http_timeout = 15
max_retry = 2
template_temp_dir = "temp/"
template_archive_dir="archive/"

delete_file_n_days_age = 3 #删除3天前的历史下载临时文件和zip文件
delete_file_cron = '00   22  *  *  0'

default_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'

ua_list = {
    'pc':[
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36',
    ],
    'ipad':[
        'Mozilla/5.0 (iPad; CPU OS 7_0 like Mac OS X) AppleWebKit/537.51.1 (KHTML, like Gecko) CriOS/30.0.1599.12 Mobile/11A465 Safari/8536.25 '
    ],
    'iphone':[
        'Mozilla/5.0 (iPhone; CPU iPhone OS 8_0 like Mac OS X) AppleWebKit/600.1.4 (KHTML, like Gecko) Version/8.0 Mobile/12A365 Safari/600.1.4'
    ],
    'android_pad':[
        'Mozilla/5.0 (Linux; Android 9.0.0; HTC D820u Build/KTU84P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2214.89 Mobile Safari/537.36'
    ],
    'android':[
        'Mozilla/5.0 (Linux; U; Android 8.0.1; zh-cn; HTC_D820u Build/KTU84P) AppleWebKit/534.30 (KHTML, like Gecko) Version/4.0 Mobile Safari/534.30'
    ]
}


page_default_encoding='utf-8'

url_download_queue_timeout = 3  # 轮询一个url超时时间
wait_url_sleep_time = 2  # 队列没有url时候等待多久
wait_download_finish_sleep = 3  # 主线程等待任务完成的每次等待时间

max_loop_cnt = 3  # 几个任务一起处理
max_task_run_tm_seconds=5*60 #一个任务最多运行多久

wait_db_task_interval_s=5

db_name = "tpl_spider"
db_user = "postgres"
db_psw = ""
db_url = "dev.jscrapy.org"
db_port = "5432"


SEND_MAIL = {
    'sender': 'kernel.h@qq.com',
    'to': ['fox@jscrapy.org'],
    'smtp_host': 'smtp.qq.com',
    'smtp_port': 465,
    'smtp_user': 'kernel.h@qq.com',
    'smtp_psw': 'pkdsnbblrrnvcagd',

}
from logging.config import fileConfig
import logging
fileConfig('logging.ini')
logger = logging.getLogger()