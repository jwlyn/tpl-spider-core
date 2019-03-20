import time
import datetime
import subprocess


def get_n_days_ago(n_days):
    """
    获取昨天的表示字符串例如"2018-02-08"
    :return:
    """
    today = datetime.date.today()
    oneday = datetime.timedelta(days=1)
    yesterday = today - oneday
    return yesterday


def get_n_days_ago_str(n_days):
    nday_age = get_n_days_ago(n_days)
    return time.strftime("%Y-%m-%d", nday_age.timetuple())


def clean_timeout_temp_dir_and_archive(n_day, parent_dir_list):
    """
    删除N天前的目录
    :n_day:
    :parent_dir_list: 父目录，删除这个目录下的超时文件
    :return:
    """
    for search_dir in parent_dir_list:
        cmd = f"""
            find {search_dir}/ -maxdepth 1 -type d -mtime +{n_day} -exec rm -rf {{}} \;
        """
        (status, output) = subprocess.getstatusoutput(cmd)

