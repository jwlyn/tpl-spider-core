import os, re
from logging.config import fileConfig
import shutil

import aioify as aioify

from utils import get_date, get_domain, get_abs_url, format_url, get_url_file_name, get_file_name_by_type, \
    is_same_web_site_link, is_img_ext
from datetime import datetime
import time
from bs4 import BeautifulSoup
import config
from queue import Queue
import threading
import aiohttp
import asyncio
import aiofiles
from config import logger


class TemplateCrawler(object):

    logger = logger
    CMD_DOWNLOAD = 'download'
    CMD_QUIT = 'quit'
    FILE_TYPE_BIN = 'bin'
    FILE_TYPE_TEXT = 'text'

    def __init__(self, url_list, save_base_dir, header, encoding=None, grab_out_site_link=False):
        self.url_list = list(set(list(map(lambda x: format_url(x), url_list))))
        self.parent_save_dir = save_base_dir
        self.date_str = get_date()
        self.zip_save_base_abs_dir = f"{self.parent_save_dir}/{config.template_archive_dir}/{self.date_str}/"  # zip /xx/xx/archive/2019-00-01/
        self.download_temp_abs_dir = f"{self.parent_save_dir}/{config.template_temp_dir}/{self.date_str}/"
        self.tpl_mapping = self.__get_tpl_replace_url(url_list)
        self.domain = get_domain(url_list[0])
        self.tpl_dl_dir, self.js_dir, self.img_dir, self.css_dir, self.other_dir = self.__prepare_dirs()
        self.dl_urls = {}  # 去重使用,存储 url=>磁盘绝对路径
        self.error_grab_resource = {}  # 记录 http url => relative url ，最后生成一个报告打包
        self.header = header
        self.charset = encoding
        self.is_grab_outer_link = grab_out_site_link
        self.download_queue = Queue()  # 数据格式json  {'cmd':quit/download, "url":'http://baidu.com', "save_path":'/full/path/file.ext', 'type':'bin/text'}
        self.download_finished = False  # url消耗完毕不代表网络请求都返回了
        self.task_finished = False  #全部网络都返回， eventloop结束

        self.thread = threading.Thread(target=self.__download_thread)
        self.thread.start()

    def __get_relative_report_file_path(self, path):
        path = path.replace("//", "/")
        return path[len(self.__get_tpl_full_path()):]

    async def __make_report(self):
        """
        1，标题
        2，源url
        3，error url
        4，ok url
        TODO js里的替换,保存原始文件和替换后文件
        :return:
        """
        report_file = f"{self.__get_tpl_full_path()}/_report.html"
        async with aiofiles.open(report_file, 'w', encoding='utf-8') as f:
            await f.writelines("""
                <center><h1>TEMPLATE REPORT</h1></center><br>\n
                
                <h2 style='color: red;'>1. Error report</h2><br>\n
            """)
            if len(self.error_grab_resource.keys()) > 0:
                for url, path in self.error_grab_resource.items():
                    await f.writelines(
                        f"{url} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; => &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {path} <br>\n")
                await f.writelines("""
                <b>To fix this error: download the url content and put them in the directory followed.</b><br>\n
            """)
            else:
                await f.writelines("All things is ok!")

                await f.writelines("""
                <hr /><br>
                <h2>2. Template source url</h2><br>\n
            """)
            for u in self.url_list:
                await f.writelines(f"<a href='{u}'>{u}</a><br>\n" )

            await f.writelines(f"""
            <hr />
            <h2>3. Spider report ({len(self.dl_urls.keys())} files)</h2><br>\n
            """ )

            for url, path in self.dl_urls.items():
                await f.writelines(
                    f"<a href='%s'>%s</a> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; =>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; %s <br>\n" % (
                        url, url, self.__get_relative_report_file_path(path)))

            await f.writelines("""
            <br><br>
            <hr/>
            <center><a href='http://template-spider.com'>web template spider</a>&nbsp;|&nbsp;<a href=''>report bug</a></center>
        """)

    def __is_dup(self, url, save_path):
        """
        放置重复抓取
        :param url:
        :param save_path:
        :return:
        """
        if url in self.dl_urls.keys():
            save_path2 = self.dl_urls.get(url)
            if save_path == save_path2:
                self.logger.info("cached %s", url)
                return True

        return False

    def __set_dup_url(self, url, file_save_path):
        self.dl_urls[url] = file_save_path

    def __get_tpl_full_path(self):
        p = f"{self.download_temp_abs_dir}/{self.tpl_dl_dir}/"
        p = p.replace("//", '/')
        return p

    def __get_tpl_dir(self):
        return self.tpl_dl_dir

    def __get_save_base_dir(self):
        return self.zip_save_base_abs_dir

    def __get_zip_relative_path(self, full_path):
        """
        /home/cxu/zip/2019-01-02/xxxx.zip   ->  2019-01-02/xxxx.zip
        :param full_path:
        :return:
        """
        zip_file = "%s.zip"% full_path[len(f'{self.parent_save_dir}')+1:]
        return zip_file

    def __get_zip_full_path(self):
        zip_base_dir = self.zip_save_base_abs_dir
        if not os.path.exists(zip_base_dir):
            os.makedirs(zip_base_dir)
        zip_file_path = f"{zip_base_dir}/{self.tpl_dl_dir}"

        return zip_file_path

    def __get_img_full_path(self):
        return f"{self.__get_tpl_full_path()}/{self.img_dir}"

    def __get_css_full_path(self):
        return f"{self.__get_tpl_full_path()}/{self.css_dir}"

    def __get_js_full_path(self):
        return f"{self.__get_tpl_full_path()}/{self.js_dir}"

    @staticmethod
    async def __async_save_text_file(content, file_abs_path, encoding='utf-8'):
        async with aiofiles.open(file_abs_path, "w", encoding=encoding) as f:
            await f.writelines(content)

    def __prepare_dirs(self):
        """
        根据域名+ts命名这个目录
        :return:
        """
        template_dir = f"{self.domain}_{datetime.now().timestamp()}"  # 日期目录/下的  域名_时间戳
        tpl_full_dir = f"{self.download_temp_abs_dir}/{template_dir}"
        dirs = [tpl_full_dir, f"{tpl_full_dir}/js", f"{tpl_full_dir}/img", f"{tpl_full_dir}/css",
                f"{tpl_full_dir}/other"]
        for d in dirs:
            if not os.path.exists(d):
                os.makedirs(d)

        return template_dir, "js", "img", "css", "other"

    def __get_file_name(self, url, i):
        return  f"index_{i}.html"

    def __get_tpl_replace_url(self, url_list):
        """
        模版中的链接地址要替换掉,生成一份 url全路径->磁盘路径的映射替换表
        :param url_list:
        :return:
        """
        url_mp = {}
        i = 0
        for u in url_list:
            url_mp[u] = self.__get_file_name(u, i)
            i += 1

        return url_mp

    def __make_template(self, soup, url):
        """
        下载到的网页里把模版链接替换掉如果有。
        :param soup:
        :param url:
        :return:
        """
        for base_tag in soup.find_all("base"):  # 删除<base>标签
            base_tag.decompose()

        a_list = soup.find_all("a")
        """
            遍历全部的链接：
            如果链接的绝对路径在url_list里：
                替换为模版的最终保存的地址
        """
        try:
            for a in a_list:
                raw_link = a.get("href")
                if raw_link is None:
                    continue
                abs_link = get_abs_url(url, raw_link)
                if abs_link in self.url_list:
                    tpl_link = self.tpl_mapping.get(abs_link)
                    a['href'] = tpl_link
        except Exception as e:
            self.logger.info("%s: %s", a, e)
            self.logger.exception(e)
            raise e

    def __log_error_resource(self, url, path):
        self.error_grab_resource[url] = path

    def __dl_js(self, soup, url):
        """
        下载js，替换html里js文件的地址
        :param soup:
        :param url:
        :return:
        """
        scripts_urls = soup.find_all("script")
        for scripts in scripts_urls:
            raw_link = scripts.get("src")
            if raw_link is None:
                continue
            abs_link = get_abs_url(url, raw_link)

            if is_same_web_site_link(url, abs_link) is True or self.is_grab_outer_link:
                """
                如果是外链引入的js就不管了,除非打开了开关
                """
                file_name = get_file_name_by_type(abs_link, ['js'])
                file_save_path = f"{self.__get_js_full_path()}/{file_name}"
                replace_url = f"{self.js_dir}/{file_name}"
                scripts['src'] = replace_url
                self.__url_enqueue(abs_link, file_save_path, self.FILE_TYPE_TEXT)

    def __dl_img(self, soup, url):
        """
        下载图片，并替换html里图片的地址
        :param soup:
        :param url:
        :return:
        """
        images = soup.find_all("img")
        for img in images:
            raw_link = img.get("src")
            if raw_link is None or raw_link.lower().strip().startswith(
                    'data:image'):  # 跳过base64内嵌图片 <img src='data:image...'/>
                continue
            abs_link = get_abs_url(url, raw_link)

            if is_same_web_site_link(url, abs_link) is True or self.is_grab_outer_link:
                file_name = get_url_file_name(abs_link)
                file_save_path = f"{self.__get_img_full_path()}/{file_name}"
                replace_url = f"{self.img_dir}/{file_name}"
                img['src'] = replace_url

                self.__url_enqueue(abs_link, file_save_path, self.FILE_TYPE_BIN)

            if img.get("crossorigin ") is not None:
                del img['crossorigin ']
            if img.get("integrity") is not None:
                del img['integrity']

    @staticmethod
    def __get_style_url_link(url_src):
        """
        url('xxxx')
        url("xxxx")
        url(xxxx)
        :param url_src:
        :return:  xxxx
        """
        url_src = url_src.strip()
        if '"' in url_src or "'" in url_src:
            return url_src[5: -2].strip()
        else:
            return url_src[4: -1].strip()

    def __dl_inner_style_img(self, soup, url):
        """
        获取到html页面内嵌样式的图片资源
        <xx style='background: url(xxxxx.jpg)'>
        :param soup:
        :param url:
        :return:
        """
        inner_style_node = soup.find_all(style=re.compile("url(.*?)"))  # TODO url/URL 大小写
        for style in inner_style_node:
            resource_url = re.findall('url\(.*?\)', style.get("style"))[0]  # TODO 遍历而非取第一个，匹配到全部
            resource_url = self.__get_style_url_link(resource_url)
            if resource_url.lower().startswith("data:image"):  # 内嵌base64图片
                continue
            abs_link = get_abs_url(url, resource_url)

            if is_same_web_site_link(url, abs_link) is True or self.is_grab_outer_link:
                file_name = get_url_file_name(abs_link)
                file_save_path = f"{self.__get_img_full_path()}/{file_name}"
                replace_url = f"{self.img_dir}/{file_name}"
                style['style'] = style['style'].replace(resource_url, replace_url)
                self.__url_enqueue(abs_link, file_save_path, self.FILE_TYPE_BIN)

    async def __dl_link(self, soup, url):
        """
        下载<link>标签里的资源，并替换html里的地址
        :param soup:
        :param url:
        :return:
        """
        css_src = soup.find_all("link")
        for css in css_src:
            raw_link = css.get("href")
            if raw_link is None:
                continue
            abs_link = get_abs_url(url, raw_link)
            if is_same_web_site_link(url, abs_link) is True or self.is_grab_outer_link:  # 控制是否抓外链资源
                file_name = get_url_file_name(abs_link)

                if is_img_ext(file_name):
                    file_save_path = f"{self.__get_img_full_path()}/{file_name}"
                    replace_url = f"{self.img_dir}/{file_name}"
                    self.__url_enqueue(abs_link, file_save_path, self.FILE_TYPE_BIN)
                else:
                    file_save_path = f"{self.__get_css_full_path()}/{file_name}"
                    replace_url = f"{self.css_dir}/{file_name}"
                    if not self.__is_dup(abs_link, file_save_path):
                        resp_text, _ = await self.__async_get_request_text(abs_link)
                        if resp_text is not None:
                            text_content = resp_text
                            text_content = self.__replace_and_grab_css_url(abs_link, text_content)
                            self.__set_dup_url(abs_link, file_save_path)
                            await self.__async_save_text_file(text_content, file_save_path)  # 存储css文件

                css['href'] = replace_url

                # 将跨域锁定和来源校验关闭
                if css.get("crossorigin") is not None:
                    del css['crossorigin']
                if css.get('integrity') is not None:
                    del css['integrity']

    def __replace_and_grab_css_url(self, url, text):
        urls = re.findall("url\(.*?\)", text)  # TODO 区分大小写
        for u in urls:
            relative_u = self.__get_style_url_link(u)
            if relative_u.lower().startswith("data:image"):  # 内嵌base64图片
                continue
            abs_link = get_abs_url(url, relative_u)
            if is_same_web_site_link(url, abs_link) is True or self.is_grab_outer_link:  # 控制是否抓外链资源
                file_name = get_url_file_name(abs_link)
                is_img = is_img_ext(file_name)
                if is_img:
                    file_save_path = f"{self.__get_img_full_path()}/{file_name}"
                    replace_url = f"../{self.img_dir}/{file_name}"
                    self.__url_enqueue(abs_link, file_save_path, self.FILE_TYPE_BIN)
                    text = text.replace(relative_u, replace_url)
                else:
                    file_save_path = f"{self.__get_css_full_path()}/{file_name}"
                    replace_url = f"{file_name}"   # 由于是相对于css文件的引入,因此是平级关系, 如果是图片就需要从../img目录下
                    self.__url_enqueue(abs_link, file_save_path, self.FILE_TYPE_BIN)
                    text = text.replace(relative_u, replace_url)

        return text

    async def __rend_template(self, url, html):
        """
        把从url抓到的html原始页面进行链接加工，图片，css,js下载
        :param url:
        :param html:
        :return:
        """
        soup = BeautifulSoup(html, "lxml")
        self.__make_template(soup, url)
        self.__dl_inner_style_img(soup, url)
        self.__dl_img(soup, url)
        for i in range(0, config.max_retry):
            try:
                await self.__dl_link(soup, url)
                break
            except:
                continue

        self.__dl_js(soup, url)
        return soup.prettify()

    def __url_enqueue(self, url='', file_save_path='', file_type='text'):
        """

        :param cmd: quit/download
        :param url: url or None
        :param file_save_path: full path or None
        :param file_type: bin/text
        :return:
        """
        file_save_path = file_save_path.replace("//", '/')
        if not self.__is_dup(url, file_save_path):
            self.download_queue.put({
                'cmd': self.CMD_DOWNLOAD,
                'url': url,
                'file_save_path': file_save_path,
                'file_type': file_type,
            })
            self.__set_dup_url(url, file_save_path)

    def __quit_cmd_enqueue(self):
        self.download_queue.put({
            'cmd': self.CMD_QUIT,
            'url': '',
            'file_save_path': '',
            'file_type': '',
        })

    def __wait_unitl_task_finished(self):
        """
        TODO 上报状态到redis里
        :return:
        """
        while True:
            if not self.download_finished:
                self.logger.info("task not finish, wait. Left %s URL.", self.download_queue.qsize())
                time.sleep(config.wait_download_finish_sleep)
                if not self.task_finished:
                    self.logger.info("url process finished, waiting request finish.")
                    time.sleep(2)
            elif self.task_finished:
                break

    async def __async_get_request_text(self, url):
        max_retry = config.max_retry
        time_out = config.http_timeout
        for i in range(1, max_retry + 1):
            to = time_out * i
            try:
                logger.info("start craw[%s] %s", i, url)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=to, headers=self.header) as resp:
                        txt =  await resp.text()
                        encoding = resp.charset
                        return txt, encoding
            except Exception as e:
                if i < max_retry:
                    continue
                else:
                    return None

    async def template_crawl(self):
        """
        把url_list里的网页全部抓出来当做模版，
        存储到save_path/${date}/目录下

        :param url_list:
        :param save_path:
        :return:
        """
        i = 0
        for url in self.url_list:
            resp_text, encoding = await self.__async_get_request_text(url)
            html = resp_text
            if self.charset is None:
                self.charset = encoding
                if self.charset is None:
                    self.charset = 'utf-8'

            tpl_html = await self.__rend_template(url, html)
            tpl_file_name = self.__get_file_name(url, i)
            save_file_path = f"{self.__get_tpl_full_path()}/{tpl_file_name}"
            await self.__async_save_text_file(str(tpl_html), save_file_path)
            self.__set_dup_url(url, save_file_path)
            i += 1

        self.__quit_cmd_enqueue()  # 没有新的url产生了
        self.__wait_unitl_task_finished() # 这个时候异步请求也全部落到磁盘上了
        await self.__make_report()
        zip_full_path = self.__get_zip_full_path()
        self.__make_zip(zip_full_path)
        await self.__clean_dl_files()
        return self.__get_zip_relative_path(zip_full_path)

    def __download_thread(self):
        """
        这个函数会在一个新的线程里协程执行
        :return:
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks = [asyncio.ensure_future(self.__async_download_url(), loop=loop),
                 asyncio.ensure_future(self.__async_download_url(), loop=loop),
                 asyncio.ensure_future(self.__async_download_url(), loop=loop),
                 asyncio.ensure_future(self.__async_download_url(), loop=loop),
                 ]
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
        self.task_finished = True

    async def __async_dl_and_save(self, url, file_save_path, file_type):
        """

        :param url:
        :return:
        """
        max_retry = config.max_retry
        time_out = config.http_timeout
        is_succ = False
        for i in range(1, max_retry + 1):
            to = time_out * i
            try:
                self.logger.info("async craw[%s] %s, file_type: %s", i, url, file_type)
                is_succ = await self.__async_spider_get(url, self.header, file_save_path, file_type, to)
                if not is_succ:
                    continue
                else:
                    return is_succ
            except asyncio.TimeoutError as te:
                self.logger.error("async retry[%s] asyncio.TimeoutError:", i)
                if i < max_retry:
                    continue
            except Exception as e:
                self.logger.error("async retry[%s] error: %s", i, e)
                self.logger.exception(e)
                if i < max_retry:
                    self.logger.info("async retry craw[%s] %s" % (i+1, url))
                    continue

    async def __async_spider_get(self, url, header, file_save_path, file_type='bin', to=10):
        async with aiohttp.ClientSession() as session:
            is_succ = await self.__do_download(session, url, header, file_save_path, file_type, to)
            return is_succ

    async def __do_download(self, session, url, header, file_save_path, file_type, to):
        async with session.get(url, timeout=to, headers=header) as response:
            if file_type == self.FILE_TYPE_TEXT:
                text = await response.text()
                await self.__async_save_text_file(text, file_save_path)
            else:
                async with aiofiles.open(file_save_path, 'wb') as fd:
                    while True:
                        chunk = await response.content.read(512)
                        if not chunk:
                            break
                        else:
                            await fd.write(chunk)

            return True

    async def __async_download_url(self):
        """

        :return:
        """
        while True:
            if self.download_finished is True:
                break
            cmd = self.download_queue.get()
            if not cmd:  # 超时没拿到东西，让出cpu然后再来拿
                self.logger.info("queue get nothing")
                time.sleep(config.url_download_queue_timeout)
                await asyncio.sleep(config.url_download_queue_timeout)
                continue

            self.logger.debug("queue get cmd %s", cmd)
            cmd_content = cmd['cmd']
            if cmd_content == self.CMD_QUIT: # 虽然这里收到了，但是不能排除其他协程还在等待网络返回
                self.logger.info("quit download task")
                self.download_finished = True
                break  # 收到最后一条命令，退出。任务结束
            else:
                url = cmd['url']
                save_path = cmd['file_save_path']
                file_type = cmd['file_type']
                is_succ = await self.__async_dl_and_save(url, save_path, file_type)

                if is_succ is False:
                    self.logger.error("async get %s error", url)
                    self.__log_error_resource(url, self.__get_relative_report_file_path(save_path))
                else:
                    self.__set_dup_url(url, save_path)

    def __make_zip(self, zip_full_path):
        shutil.make_archive(zip_full_path, 'zip', self.download_temp_abs_dir, base_dir=self.__get_tpl_dir())
        self.logger.info(f"zip file {zip_full_path}.zip make ok")

    async def __clean_dl_files(self):
        aioshutil = aioify(obj=shutil, name='aishutil')
        try:
            #dir_to_del =
            await aioshutil.rmtree(self.__get_tpl_full_path(), ignore_errors=True)
            #shutil.rmtree(self.__get_tpl_full_path(), ignore_errors=True)
        except Exception as e:
            self.logger.error(e)
        pass


if __name__ == "__main__":
    fileConfig('logging.ini')
    """
    动态渲染的： 'https://docs.python.org/3/library/os.html',http://www.gd-n-tax.gov.cn/gdsw/index.shtml
    需要UA：'https://stackoverflow.com/questions/13137817/how-to-download-image-using-requests',
    gb2312 : https://www.jb51.net/web/25623.html
    """
    url_list = [
        # 'https://stackoverflow.com/questions/13137817/how-to-download-image-using-requests',
        # 'http://boke1.wscso.com/',
        # 'https://www.sfmotors.com/',
        # 'https://www.sfmotors.com/company',
        # 'https://www.sfmotors.com/technology',
        # 'https://www.sfmotors.com/vehicles',
        # 'https://www.sfmotors.com/manufacturing'
        'https://www.getreplacer.com/index.html',
        'https://www.getreplacer.com/icons.html',
        'https://www.getreplacer.com/template-1.html',
        'https://www.getreplacer.com/template-2.html',
        'https://www.getreplacer.com/template-3.html',
        'https://www.getreplacer.com/template-4.html',
        'https://www.getreplacer.com/template-5.html',
        'https://www.getreplacer.com/template-6.html',
        'https://www.getreplacer.com/template-7.html',
        'https://www.getreplacer.com/template-8.html',
        'https://www.getreplacer.com/template-9.html',

        'https://www.getreplacer.com/page-about.html',
        'https://www.getreplacer.com/page-features.html',
        'https://www.getreplacer.com/page-faq.html',
        'https://www.getreplacer.com/page-login.html',
        'https://www.getreplacer.com/page-register.html',
        'https://www.getreplacer.com/page-404.html',
        'https://www.getreplacer.com/page-soon.html',
        'https://www.getreplacer.com/page-blog.html',
        'https://www.getreplacer.com/page-blog-entry.html',


    ]
    n1 = datetime.now()
    spider = TemplateCrawler(url_list, save_base_dir=config.template_temp_dir, header={'User-Agent': config.default_ua},
                             grab_out_site_link=True)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(
        spider.template_crawl()
    ))
    loop.close()
    n2 = datetime.now()
    print(n2 - n1)
