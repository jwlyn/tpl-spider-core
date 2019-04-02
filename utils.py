import base64
from datetime import datetime
from urllib.parse import urlparse, urljoin
import uuid,os,time, random
import tldextract
from email.mime.text import MIMEText
from email.header import Header
from config import SEND_MAIL
from smtplib import SMTP_SSL
import logging,re
from slugify import slugify
import validators
import mimetypes

"""
urlparse.urlparse("http://some.page.pl/nothing.py;someparam=some;otherparam=other?query1=val1&query2=val2#frag")
ParseResult(scheme='http', netloc='some.page.pl', path='/nothing.py', params='someparam=some;otherparam=other', query='query1=val1&query2=val2', fragment='frag')
"""

logger = logging.getLogger()


def get_date():
    return datetime.now().strftime("%Y-%m-%d")


def get_domain(url):
    """
    some.page.pl
    :param url:
    :return:
    """
    ret = urlparse(url)
    return format_url(ret.netloc)


def get_base_url(url):
    """
    http://some.page.pl
    :param url:
    :return:
    """
    ret = urlparse(url)
    u = "%s://%s"%(ret.schema, ret.netloc)
    return format_url(u)


def format_url(url):
    """
    除去末尾的/, #
    :param url:
    :return:
    """
    ret = urlparse(url)
    fragments = ret.fragment
    url = url[0:len(url)-len(fragments)]
    if url.endswith('/') or url.endswith("#"):
        url = url[:-1]

    return url


def get_abs_url(base_url, raw_link):
    """
    如果raw_link和base_url不是一个站点的就会返回raw_link本身
    :param base_url:
    :param raw_link:
    :return:
    """
    u = urljoin(base_url, raw_link.strip())
    return format_url(u)



def __get_uniq_timestr():
    str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    uniq = random.randint(10, 9999)
    return "%s.%s" % (str, uniq)


def get_url_file_name(url, file_ext='css'):
    """
    http://a.com?main.css?a=b;c=d;
    http://a.com/a/b/c/xx-dd;a=c;b=d
    http://res.weiunity.com/template/boke1/resource/fonts/icomoon.ttf?ngfxmq
    'https://upload.jianshu.io/users/upload_avatars/8739889/da9dcd2a-3a25-49fa-a0db-ed752b7bc6f8.png?imageMogr2/auto-orient/strip|imageView2/1/w/96/h/96'
    https://fonts.googleapis.com/css?family=Open+Sans:300,400,600,700,800
    https://www.googletagmanager.com/gtag/js?id=UA-122907869-1
    :param url:
    :return:
    """
    i = url.rfind("?")
    if i>0:
        start_i = url[0:i].rfind("/")
        file_name = url[start_i+1:i]
        # return file_name
        if "." not in file_name:
            file_name = f'{file_name}-{__get_uniq_timestr()}'
            file_name = slugify(f"{file_name}.{file_ext}")
        return file_name

    i = url.rfind("=")
    if i>0:
        file_name = url[i + 1:]
    else:
        i = url.rfind("/")
        file_name = url[i + 1:]

    if file_name.find(".")<0:
        file_name = f'{file_name}.{file_ext}'
    return file_name


def is_same_web_site_link(url1, url2):
    info1 = tldextract.extract(url1)
    info2 = tldextract.extract(url2)
    domain1 = f'{info1[0]}.{info1[1]}.{info1[2]}'
    domain2 = f'{info2[0]}.{info2[1]}.{info2[2]}'

    return domain1==domain2


def is_valid_url(url):
    # regex = re.compile(
    #     r'^(?:http|ftp)s?://'  # http:// or https://
    #     r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    #     r'localhost|'  # localhost...
    #     r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    #     r'(?::\d+)?'  # optional port
    #     r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    # re.match(regex, url)
    return validators.url(url)

def format_url(url):
    i=url.rfind("#")
    if i!= -1:
        url = url[:i]

    return url


def is_under_same_link_folder(url1, url2):
    """
    检查url1是否在url2的想同或者下一层级
    :param url1:
    :param url2:
    :return:
    """
    url1 = url1[:url1.rfind("/")]
    url2 = url2[:url2.rfind("/")]
    return url1.startswith(url2)


def __get_file_ext(file_name):
    _, file_extension = os.path.splitext(file_name)
    return file_extension[1:]


def is_img_ext(file_name):
    return file_name.lower().endswith(('gif','jpg','jpeg','png','swf','psd','bmp','tiff',\
                                       'jpc','jp2','jpf','jb2','swc','aiff','wbmp','xbm',\
                                       'tif','jfif','ras','cmx','ico','cod','pnm',\
                                       'pbm','pgm','xwd','fh','wbmp','svg','aiff','webp'))


def is_page_url(a_href):
    """
    有的url是Email地址，这个没办法抓
    :param a_href:
    :return:
    """
    if a_href and not a_href.lower().startswith(("mailto:", "tel:", "javascript:", "ftp:", "file:")):
        return True
    else:
        return False


def is_inline_resource(resource_content):
    """

    url(data:application/x-font-ttf;charset=utf-8;base64,AAEAAA)
    url(data:image)
    :param resource_content:
    :return:
    """
    return resource_content and resource_content.lower().startswith(("data:", ))


def send_template_mail(title, template_file, args, to_list):
    content = ""
    with open(template_file) as f:
        content = f.readlines()
        content = ''.join(content)
    for k, v in args.items():
        content = content.replace(k, v)

    send_email(title, content, to_list)


def send_email(title, content, to_list):
    # 三个参数：第一个为文本内容，第二个 plain 设置文本格式，第三个 utf-8 设置编码
    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = Header(f"{SEND_MAIL['sender']}", 'utf-8')
    message['To'] = Header("代理池管理员", 'utf-8')
    message['Subject'] = Header(title, 'utf-8')

    try:
        smtpObj = SMTP_SSL(SEND_MAIL['smtp_host'], SEND_MAIL['smtp_port'])
        smtpObj.login(SEND_MAIL['smtp_user'], SEND_MAIL['smtp_psw'])
        smtpObj.sendmail(SEND_MAIL['sender'], to_list, message.as_string())
        logger.info("Successfully sent email")
    except Exception as e:
        logger.error("Error: unable to send email")


def get_file_name_from_url(url, duper, ext='css'):
    temp = urlparse(url)
    path = temp.path
    q = temp.query
    if len(path)>1:
        base_file_name = os.path.basename(path)
    else:
        base_file_name = os.path.basename(q)

    if len(base_file_name) <=0:
        base_file_name = __get_uniq_timestr()

    p = re.compile("[\"'|\\/*:?<>]")
    base_file_name = re.sub(p, "-", base_file_name)

    if '.' not in base_file_name:
        base_file_name = f"{base_file_name}.{ext}"

    while base_file_name in duper:
        base_file_name = f'1_{base_file_name}'

    duper.append(base_file_name)

    return base_file_name


def __get_inline_data_url_types(ext):
    if ext in ['svg']:
        return f"{ext}+xml"
    else:
        return ext


def base64_encode_resource(css_path,   file_name):
    """
    用base64编码文件
    :param file_path:
    :return:
    """

    f_name, file_extension = os.path.splitext(file_name)
    if is_img_ext(file_extension):
        ext = file_extension[1:]
        ext = __get_inline_data_url_types(ext)
        file_type = f"image/{ext}"
        file_path = f"{css_path}/{file_name}"
    else:
        file_type = f"application/x-font-{file_extension[1:]}"
        file_path = f"{css_path}/{file_name}"

    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            b64_str = base64.b64encode(f.read()).decode('ascii')
    else:
        b64_str = f'{file_name} DOWNLOAD_ERROR'

    return b64_str, file_type


if __name__=="__main__":
    urls_test = [
    "http://markup.themewagon.com/mountain_v_2.5.3/assets/lib/menuzord/css/menuzord.css",
    "http://a.com?main.css?a=b;c=d;",
    "http://a.com/a/b/c/xx-dd;a=c;b=d",
    "http://res.weiunity.com/template/boke1/resource/fonts/icomoon.ttf?ngfxmq",
    "https://upload.jianshu.io/users/upload_avatars/8739889/da9dcd2a-3a25-49fa-a0db-ed752b7bc6f8.png?imageMogr2/auto-orient/strip|imageView2/1/w/96/h/96'",
    "https://fonts.googleapis.com/css?family=Open+Sans:300,400,600,700,800",
    "https://www.googletagmanager.com/gtag/js?id=UA-122907869-1",
    "https://fu.com/a/ttdd.html",
    "http://g.alicdn.com/??kissy/k/6.2.4/seed-min.js,kg/global-util/1.0.7/index-min.js,tb/tracker/4.3.12/index.js,kg/tb-nav/2.5.3/index-min.js,secdev/sufei_data/3.3.5/index.js",
    ]
    for u in urls_test:
        print(get_file_name_from_url(u, []))
