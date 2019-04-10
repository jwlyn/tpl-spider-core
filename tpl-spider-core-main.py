import asyncio
import sys

import asyncpg
from config import logger
import threading
import config
import config as dbconfig
import json
from schedule_task import clean_timeout_temp_dir_and_archive
from template_crawl import TemplateCrawler
import random
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from utils import send_template_mail


class SpiderTask(object):
    """
    主要是从数据源选择数据，然后运行抓取工作。
    """
    async def __get_task_by_sql(self, sql):
        conn = await asyncpg.connect(database=dbconfig.db_name, user=dbconfig.db_user, password=dbconfig.db_psw,
                                     host=dbconfig.db_url, )

        try:
            async with conn.transaction(isolation='repeatable_read'):
                row = await conn.fetchrow(sql)
        except asyncpg.SerializationError as se:
            row = None
        except Exception as e:
            logger.exception(e)
            row = None
        finally:
            if conn:
                await conn.close()

        if row:
            r = row
            task = {
                'id': r[0],
                'seeds': json.loads(r[1]),
                'ip': r[2],
                'email': r[3],
                'user_agent': r[4],
                'status': r[5],
                'is_grab_out_link': r[6],
                'is_to_single_page': r[7],
                'is_full_site': r[8],
                'is_ref_model': r[9],
                'gmt_modified': r[10],
                'gmt_created': r[11],
                'file_id': r[12],
                'encoding': r[13],
                'to_framework': r[14],
            }
        else:
            task = None

        return task

    async def __get_timeout_task(self):
        sql = f"""
            -- start transaction isolation level repeatable read;
            update spider_task set gmt_modified = NOW() where id in (
                select id
                from spider_task
                where status ='P' AND gmt_modified + '{config.max_task_run_tm_seconds} seconds'::INTERVAL < NOW()
                order by gmt_created DESC 
                limit 1
            )
            returning id, seeds, ip, email, user_agent, status, is_grab_out_link, is_to_single_page, is_full_site, is_ref_model, gmt_modified, gmt_created,file_id, encoding,to_framework;
            -- commit;
        """
        return await self.__get_task_by_sql(sql)

    async def __get_a_task(self):
        sql = """
            -- start transaction isolation level repeatable read;
            update spider_task set status = 'P', gmt_modified=NOW() where id in (
                select id
                from spider_task
                where status ='I'
                order by gmt_created DESC 
                limit 1
            )
            returning id, seeds, ip, email, user_agent, status, is_grab_out_link,is_to_single_page, is_full_site, is_ref_model, gmt_modified, gmt_created, file_id, encoding, to_framework;
            -- commit;
        """
        return await self.__get_task_by_sql(sql)

    async def __update_task_status(self, task_id, status='C', zip_path=None, error=None):
        conn = await asyncpg.connect(database=dbconfig.db_name, user=dbconfig.db_user, password=dbconfig.db_psw,
                                     host=dbconfig.db_url, )
        if zip_path is None:
            zip_path = "null"
        if error is None:
            error = "null"
        try:
            sql = f"""
                update spider_task set status = '{status}', result='{zip_path}', error={error} where id = '{task_id}';
            """
            logger.info("execute sql %s", sql)
            await conn.execute(sql)
            # logger.info("execute sql %s", sql)
        except Exception as e:
            logger.exception(e)
        finally:
            if conn:
                await conn.close()

    def __get_user_agent(self, key):
        ua_list = config.ua_list.get(key)
        if ua_list is None:
            ua = config.default_ua
        else:
            return random.choice(ua_list)

        return ua

    async def loop(self, base_craw_file_dir):
        while True:
            task = await self.__get_timeout_task()  # 优先处理超时的任务

            if task is not None:
                logger.info("获得一个超时任务 %s", task['id'])
            else:
                task = await self.__get_a_task()
                if not task:
                    logger.info("no task, wait")
                    await asyncio.sleep(config.wait_db_task_interval_s)
                    continue
                else:
                    logger.info("获得一个正常任务 %s", task['id'])

            seeds = task['seeds']
            task_id = task['id']
            is_grab_out_site_link = task['is_grab_out_link']  # 是否抓取外部站点资源
            is_to_single_page = task['is_to_single_page']
            is_full_site = task['is_full_site']
            is_ref_model = task['is_ref_model']
            encoding = task['encoding']
            to_framework = task['to_framework']
            user_agent = self.__get_user_agent(task['user_agent'])
            spider = TemplateCrawler(seeds, save_base_dir=f"{base_craw_file_dir}/",
                                     header={'User-Agent': user_agent},
                                     encoding=encoding,
                                     grab_out_site_link=is_grab_out_site_link,
                                     to_single_page=is_to_single_page,
                                     full_site=is_full_site,
                                     ref_model=is_ref_model,
                                     framework=to_framework
                                     )
            try:
                await asyncio.wait_for(spider.template_crawl(), timeout=config.max_task_run_tm_seconds)
                template_zip_file = spider.zip_result_file
            except asyncio.TimeoutError:
                await send_template_mail("your task is failed", 'email_template/task_fail.html')
                await self.__update_task_status(task_id,  status="E", error="任务运行超过设定的最大运行时间")
                continue

            logger.info("begin update task finished")
            await self.__update_task_status(task_id, status='C', zip_path=template_zip_file)
            await send_template_mail("your template is ready", "email_template/email-download.html",
                                     {"{{template_id}}": task['file_id']}, task['email'])
            logger.info("send email to %s, link: %s", task['email'], task['file_id'])


def setup_schedule_task(n_days_age, search_parent_dir_list):
    time_zone = timezone("Asia/Shanghai")
    scheduler = BackgroundScheduler(timezone=time_zone)
    trigger = CronTrigger.from_crontab(config.delete_file_cron, timezone=time_zone)
    scheduler.add_job(clean_timeout_temp_dir_and_archive, trigger,
                      kwargs={"n_day": n_days_age, "parent_dir_list": search_parent_dir_list})
    # 启动时清理一下
    clean_timeout_temp_dir_and_archive(n_days_age, search_parent_dir_list)


async def main(base_craw_file_dir):
    task = []
    for i in range(0, config.max_loop_cnt):
        task.append(SpiderTask().loop(base_craw_file_dir))
    await asyncio.gather(*task)


if __name__ == "__main__":
    logger.info("tpl-spider-web start, thread[%s]" % threading.current_thread().getName())
    base_craw_file_dir = sys.argv[1]
    logger.info("基本目录是%s", base_craw_file_dir)
    if not base_craw_file_dir:
        logger.error("没有指明模版压缩文件的目录")
        exit(-1)

    setup_schedule_task(config.delete_file_n_days_age, [f'{base_craw_file_dir}/{config.template_temp_dir}',
                                                        f'{base_craw_file_dir}/{config.template_archive_dir}'])
    asyncio.run(main(base_craw_file_dir))
