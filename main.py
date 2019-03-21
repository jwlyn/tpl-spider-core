"""
命令行接口
"""
import fire
from template_crawl import TemplateCrawler

if __name__ == '__main__':
  fire.Fire(TemplateCrawler)
