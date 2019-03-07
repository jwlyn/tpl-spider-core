import asyncio

from config import logger
from multiprocessing import Process
import threading
import config
import config as dbconfig
import time
import json
from template_crawl import TemplateCrawler
import psycopg2
import random

from utils import send_email

"""

"""

db = psycopg2.connect(database=dbconfig.db_name, user=dbconfig.db_user, password=dbconfig.db_psw,
                      host=dbconfig.db_url, port=dbconfig.db_port)


def __get_task_by_sql(sql):
    cursor = db.cursor()
    cursor.execute(sql)
    db.commit()
    row = cursor.fetchone()
    if row is None:
        return None

    r = row
    cursor.close()
    task = {
        'id': r[0],
        'seeds': json.loads(r[1]),
        'ip': r[2],
        'user_id_str': r[3],
        'user_agent': r[4],
        'status': r[5],
        'is_grab_out_link': r[6],
        'gmt_modified': r[7],
        'gmt_created': r[8],
        'file_id': r[9],
    }

    return task


def __get_timeout_task():
    sql = """
        update spider_task set gmt_modified = NOW() where id in (
            select id
            from spider_task
            where status ='P' AND gmt_modified + '10 minutes'::INTERVAL < NOW()
            order by gmt_created DESC 
            limit 1
        )
        returning id, seeds, ip, user_id_str, user_agent, status, is_grab_out_link, gmt_modified, gmt_created,file_id;
    """
    return __get_task_by_sql(sql)


def __get_a_task():
    sql = """
        update spider_task set status = 'P', gmt_modified=NOW() where id in (
            select id
            from spider_task
            where status ='I'
            order by gmt_created DESC 
            limit 1
        )
        returning id, seeds, ip, user_id_str, user_agent, status, is_grab_out_link, gmt_modified, gmt_created, file_id;
    """
    return __get_task_by_sql(sql)


def __update_task_finished(task_id, zip_path, status='C'):
    sql = f"""
        update spider_task set status = '{status}', result='{zip_path}' where id = '{task_id}'
    """
    cursor = db.cursor()
    cursor.execute(sql)
    cursor.close()
    db.commit()


def __get_user_agent(key):
    ua_list = config.ua_list.get(key)
    if ua_list is None:
        ua = config.default_ua
    else:
        return random.choice(ua_list)

    return ua


async def __do_process():

    while True:
        task = __get_timeout_task()  # 优先处理超时的任务
        if task is None:
            task = __get_a_task()
        else:
            logger.info("获得一个超时任务 %s", task['id'])

        if not task:
            logger.info("no task, wait")
            time.sleep(10)
            continue
        else:
            logger.info("获得一个正常任务 %s", task['id'])

        seeds = task['seeds']
        is_grab_out_site_link = task['is_grab_out_link'] #是否抓取外部站点资源
        user_agent = __get_user_agent(task['user_agent'])
        spider = TemplateCrawler(seeds, save_base_dir=config.template_base_dir,
                                 header={'User-Agent': user_agent},
                                 grab_out_site_link=is_grab_out_site_link)
        template_zip_file = await spider.template_crawl()
        __update_task_finished(task['id'], template_zip_file)
        send_email("web template download link", f"http://template-spider.com/template/{task['file_id']}", task['user_id_str'])


def __process_thread():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(
        __do_process(),
    ))
    loop.close()


def __create_process():
    process_arr = []
    process_cnt = config.max_spider_process

    for i in range(0, process_cnt):
        p = Process(target=__process_thread)
        process_arr.append(p)
        p.start()

    return process_arr


if __name__ == "__main__":
    logger.info("tpl-spider-web start, thread[%s]"% threading.current_thread().getName())
    process = __create_process()
    while True:
        time.sleep(100)
    db.close()
