
## TODO

- main 命令行接口
- 单文件模版模式
- 任务时间、大文件控制
- 页面内css资源
- 盗链模式
    - html内link (css, 图片、js等改为绝对地址)、元素style内联的资源地址修改
- 域名黑名单：不抓这些域名的东西
- 预处理页面步骤，删掉一些没用的节点：统计，dns,...

## BUG
- 百度按钮歪了
- is_same_web_site_link() 子域名不应该是父域名想同
## 竞品
https://gitee.com/mail_osc/templatespider


## 4种下载模式
1. 是否抓外网链接：引入的cdn图片，css, js是否要抓到本地来。如果抓到本地就会地柜处理css包含的url, import等引入的
2. 是否全站：抓取一个url平级和下级全部html页面。适合抓模版网站
3. 是否压缩为一个文件：图片、字体压缩进css文件，然后css、js、图片文件再压缩进html。适合发送email
4. 是否资源采用盗链方式：图片,css等都从外网引入，不走自己服务器流量

对于模式1，需要修正页面中引入外站js, image, link链接为绝对链接