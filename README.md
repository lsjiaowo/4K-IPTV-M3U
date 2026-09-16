## 4K-IPTV-M3U

基于组播源的省级直播列表仓库，按省份自动生成 `m3u/txt` 文件，并在 README 中展示可直接使用和复制的播放列表链接。
### 咪咕源 实时更新 https://gh-proxy.org/https://github.com/jia070310/lemonTV/blob/main/iptv-fe.m3u
### 相关播放器项目

- 纯直播 APP: [lemonTV](https://github.com/jia070310/lemonTV)
- 影视+直播集合版: [lomenTV-VDS](https://github.com/jia070310/lomenTV-VDS)
- Windows 直播播放器: [lemonIPTV-windows](https://github.com/jia070310/lemonIPTV-windows)



### 仓库内容

- `rtp/b.py`: 组播源抓取与生成主脚本（支持电信/移动/联通多源提取）
- `m3u/`: 自动生成的 M3U 文件
- `txt/`: 自动生成的 TXT 文件
- `.github/workflows/`: 定时任务与自动更新流程

### 更新机制

- 定时任务执行后自动更新 `m3u`、`txt`
- M3U 播放列表自动同步至 Secret Gist
- 同步自动重写 README 文件列表（含“最近更新时间”）
- M3U 订阅地址统一使用 Secret Gist RAW 固定地址
- TXT 文件保留在 Private 仓库中，通过仓库链接查看

### 本地运行

```bash
pip install -r requirements.txt
python rtp/b.py
```

## 链接说明

M3U 播放列表使用 Secret Gist RAW 固定地址，可直接复制到播放器中使用。  
TXT 文件继续保存在 Private 仓库中，登录 GitHub 后可通过仓库链接查看。  
GitHub README 不支持可执行脚本，`onclick` 复制按钮会失效，因此继续使用“可复制直链”文本（手动复制即可）。

---

## M3U 文件列表

### 电信

<table style="width:100%; table-layout:auto;">
<colgroup>
<col style="width: 220px;" />
<col style="width: 120px;" />
<col style="width: 170px;" />
<col />
</colgroup>
<thead>
<tr>
<th style="white-space:nowrap;">文件名</th>
<th style="white-space:nowrap;">播放链接</th>
<th style="white-space:nowrap;">最近更新时间</th>
<th style="white-space:nowrap;">可复制直链</th>
</tr>
</thead>
<tbody>
<tr><td style="white-space:nowrap;">上海电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E4%B8%8A%E6%B5%B7%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 17:50:44</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/上海电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">北京电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%8C%97%E4%BA%AC%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 17:27:09</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/北京电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">四川电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%9B%9B%E5%B7%9D%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:02:41</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/四川电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">四川电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%9B%9B%E5%B7%9D%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 06:08:51</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/四川电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">安徽电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%AE%89%E5%BE%BD%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:10:11</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/安徽电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">安徽电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%AE%89%E5%BE%BD%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:10:11</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/安徽电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山东电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E4%B8%9C%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 18:06:28</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山东电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山西电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E8%A5%BF%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:12:09</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山西电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山西电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E8%A5%BF%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:12:09</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山西电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">广东电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B9%BF%E4%B8%9C%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 21:20:43</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/广东电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">广东电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B9%BF%E4%B8%9C%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 21:55:20</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/广东电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">江西电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B1%9F%E8%A5%BF%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 18:02:10</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/江西电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">河北电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B2%B3%E5%8C%97%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 00:41:18</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/河北电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">河北电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B2%B3%E5%8C%97%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:22:56</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/河北电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">河南电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B2%B3%E5%8D%97%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 18:11:06</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/河南电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">浙江电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B5%99%E6%B1%9F%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 12:02:17</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/浙江电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">浙江电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B5%99%E6%B1%9F%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 21:37:09</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/浙江电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">海南电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B5%B7%E5%8D%97%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 17:06:38</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/海南电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">海南电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B5%B7%E5%8D%97%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 17:06:38</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/海南电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">湖北电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B9%96%E5%8C%97%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 09:08:00</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/湖北电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">湖北电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B9%96%E5%8C%97%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-14 13:06:07</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/湖北电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">湖南电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B9%96%E5%8D%97%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 17:20:07</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/湖南电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">福建电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E7%A6%8F%E5%BB%BA%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-09 18:11:20</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/福建电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">重庆电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%87%8D%E5%BA%86%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 18:17:55</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/重庆电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">重庆电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%87%8D%E5%BA%86%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 18:17:55</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/重庆电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">陕西电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%99%95%E8%A5%BF%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 06:17:51</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/陕西电信.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">陕西电信1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%99%95%E8%A5%BF%E7%94%B5%E4%BF%A11.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 06:17:51</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/陕西电信1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">青海电信.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%9D%92%E6%B5%B7%E7%94%B5%E4%BF%A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 18:31:42</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/青海电信.m3u</code></td></tr>
</tbody>
</table>

### 联通

<table style="width:100%; table-layout:auto;">
<colgroup>
<col style="width: 220px;" />
<col style="width: 120px;" />
<col style="width: 170px;" />
<col />
</colgroup>
<thead>
<tr>
<th style="white-space:nowrap;">文件名</th>
<th style="white-space:nowrap;">播放链接</th>
<th style="white-space:nowrap;">最近更新时间</th>
<th style="white-space:nowrap;">可复制直链</th>
</tr>
</thead>
<tbody>
<tr><td style="white-space:nowrap;">上海联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E4%B8%8A%E6%B5%B7%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:37:38</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/上海联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">北京联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%8C%97%E4%BA%AC%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 01:13:50</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/北京联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">北京联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%8C%97%E4%BA%AC%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 22:51:00</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/北京联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">四川联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%9B%9B%E5%B7%9D%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 21:26:06</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/四川联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">天津联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%A4%A9%E6%B4%A5%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 12:02:05</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/天津联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">天津联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%A4%A9%E6%B4%A5%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 22:56:26</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/天津联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山东联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E4%B8%9C%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 22:59:56</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山东联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山东联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E4%B8%9C%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 22:59:56</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山东联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山西联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E8%A5%BF%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:04:11</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山西联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">山西联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E5%B1%B1%E8%A5%BF%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:04:11</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/山西联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">河北联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B2%B3%E5%8C%97%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-11 01:34:01</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/河北联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">河南联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B2%B3%E5%8D%97%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:13:11</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/河南联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">河南联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B2%B3%E5%8D%97%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 04:32:08</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/河南联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">海南联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B5%B7%E5%8D%97%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-16 09:38:35</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/海南联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">海南联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E6%B5%B7%E5%8D%97%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-11 17:02:12</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/海南联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">辽宁联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E8%BE%BD%E5%AE%81%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:29:52</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/辽宁联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">重庆联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%87%8D%E5%BA%86%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:19:14</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/重庆联通.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">重庆联通1.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%87%8D%E5%BA%86%E8%81%94%E9%80%9A1.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:19:14</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/重庆联通1.m3u</code></td></tr>
<tr><td style="white-space:nowrap;">黑龙江联通.m3u</td><td style="white-space:nowrap;"><a href="https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/%E9%BB%91%E9%BE%99%E6%B1%9F%E8%81%94%E9%80%9A.m3u">播放链接</a></td><td style="white-space:nowrap;">2026-09-15 23:22:24</td><td><code>https://gist.githubusercontent.com/lsjiaowo/151462a1b2deeb3816e2f4ce3b3b44b1/raw/黑龙江联通.m3u</code></td></tr>
</tbody>
</table>
## TXT 文件列表

### 电信

<table style="width:100%; table-layout:auto;">
<colgroup>
<col style="width: 220px;" />
<col style="width: 120px;" />
<col style="width: 170px;" />
<col />
</colgroup>
<thead>
<tr>
<th style="white-space:nowrap;">文件名</th>
<th style="white-space:nowrap;">仓库链接</th>
<th style="white-space:nowrap;">最近更新时间</th>
<th style="white-space:nowrap;">可复制直链</th>
</tr>
</thead>
<tbody>
<tr><td style="white-space:nowrap;">上海电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E4%B8%8A%E6%B5%B7%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 17:50:44</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/上海电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">北京电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%8C%97%E4%BA%AC%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 17:27:09</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/北京电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">四川电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%9B%9B%E5%B7%9D%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:02:41</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/四川电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">四川电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%9B%9B%E5%B7%9D%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 06:08:51</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/四川电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">安徽电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%AE%89%E5%BE%BD%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:10:11</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/安徽电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">安徽电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%AE%89%E5%BE%BD%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:10:11</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/安徽电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山东电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E4%B8%9C%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 18:06:28</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山东电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山西电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E8%A5%BF%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:12:09</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山西电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山西电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E8%A5%BF%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:12:09</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山西电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">广东电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B9%BF%E4%B8%9C%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 21:20:43</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/广东电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">广东电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B9%BF%E4%B8%9C%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 21:55:20</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/广东电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">江西电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B1%9F%E8%A5%BF%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 18:02:10</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/江西电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">河北电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B2%B3%E5%8C%97%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 00:41:18</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/河北电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">河北电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B2%B3%E5%8C%97%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:22:56</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/河北电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">河南电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B2%B3%E5%8D%97%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 18:11:06</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/河南电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">浙江电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B5%99%E6%B1%9F%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 12:02:17</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/浙江电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">浙江电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B5%99%E6%B1%9F%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 21:37:09</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/浙江电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">海南电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B5%B7%E5%8D%97%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 17:06:38</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/海南电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">海南电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B5%B7%E5%8D%97%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 17:06:38</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/海南电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">湖北电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B9%96%E5%8C%97%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 09:08:00</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/湖北电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">湖北电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B9%96%E5%8C%97%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-14 13:06:07</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/湖北电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">湖南电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B9%96%E5%8D%97%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 17:20:07</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/湖南电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">福建电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E7%A6%8F%E5%BB%BA%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-09 18:11:20</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/福建电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">重庆电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%87%8D%E5%BA%86%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 18:17:55</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/重庆电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">重庆电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%87%8D%E5%BA%86%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 18:17:55</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/重庆电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">陕西电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%99%95%E8%A5%BF%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 06:17:51</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/陕西电信.txt</code></td></tr>
<tr><td style="white-space:nowrap;">陕西电信1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%99%95%E8%A5%BF%E7%94%B5%E4%BF%A11.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 06:17:51</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/陕西电信1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">青海电信.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%9D%92%E6%B5%B7%E7%94%B5%E4%BF%A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 18:31:42</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/青海电信.txt</code></td></tr>
</tbody>
</table>

### 联通

<table style="width:100%; table-layout:auto;">
<colgroup>
<col style="width: 220px;" />
<col style="width: 120px;" />
<col style="width: 170px;" />
<col />
</colgroup>
<thead>
<tr>
<th style="white-space:nowrap;">文件名</th>
<th style="white-space:nowrap;">仓库链接</th>
<th style="white-space:nowrap;">最近更新时间</th>
<th style="white-space:nowrap;">可复制直链</th>
</tr>
</thead>
<tbody>
<tr><td style="white-space:nowrap;">上海联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E4%B8%8A%E6%B5%B7%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:37:38</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/上海联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">北京联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%8C%97%E4%BA%AC%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 01:13:50</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/北京联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">北京联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%8C%97%E4%BA%AC%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 22:51:00</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/北京联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">四川联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%9B%9B%E5%B7%9D%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 21:26:06</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/四川联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">天津联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%A4%A9%E6%B4%A5%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 12:02:05</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/天津联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">天津联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%A4%A9%E6%B4%A5%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 22:56:26</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/天津联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山东联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E4%B8%9C%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 22:59:56</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山东联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山东联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E4%B8%9C%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 22:59:56</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山东联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山西联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E8%A5%BF%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:04:11</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山西联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">山西联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E5%B1%B1%E8%A5%BF%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:04:11</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/山西联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">河北联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B2%B3%E5%8C%97%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-11 01:34:01</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/河北联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">河南联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B2%B3%E5%8D%97%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:13:11</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/河南联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">河南联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B2%B3%E5%8D%97%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 04:32:08</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/河南联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">海南联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B5%B7%E5%8D%97%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-16 09:38:35</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/海南联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">海南联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E6%B5%B7%E5%8D%97%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-11 17:02:12</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/海南联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">辽宁联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E8%BE%BD%E5%AE%81%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:29:52</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/辽宁联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">重庆联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%87%8D%E5%BA%86%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:19:14</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/重庆联通.txt</code></td></tr>
<tr><td style="white-space:nowrap;">重庆联通1.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%87%8D%E5%BA%86%E8%81%94%E9%80%9A1.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:19:14</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/重庆联通1.txt</code></td></tr>
<tr><td style="white-space:nowrap;">黑龙江联通.txt</td><td style="white-space:nowrap;"><a href="https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/%E9%BB%91%E9%BE%99%E6%B1%9F%E8%81%94%E9%80%9A.txt">查看文件</a></td><td style="white-space:nowrap;">2026-09-15 23:22:24</td><td><code>https://github.com/lsjiaowo/4K-IPTV-M3U/blob/main/txt/黑龙江联通.txt</code></td></tr>
</tbody>
</table>
---

## 免责声明

- 本仓库中的频道地址来源于网络公开信息抓取与整理，仅供技术学习、测试与研究使用。
- 本仓库不存储、不制作任何视频内容，不提供任何视听节目传播服务。
- 链接可用性与内容合法性由源站提供方负责，可能随时失效或变更。
- 使用者应遵守所在地法律法规及相关版权要求，因使用本仓库内容产生的风险与责任由使用者自行承担。
