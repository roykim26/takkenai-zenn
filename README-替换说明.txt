1. 先备份当前 zenn-bot 目录。
2. 用本包里的同名文件覆盖原目录。
3. 不要覆盖你现有的 .env，只把 .env.example 里的新增字段补进去。
4. 飞书表请补通用回写字段：article_title, article_excerpt, article_url, edit_url, platform_post_id, published_at, last_push_at, last_result。
5. Hatena 第一版默认直发，不走 GitHub，不上传图片；Zenn 保持当前 GitHub 自动部署模式。
6. 如果只想先跑某一个平台，把 TARGET_PLATFORM 设为 zenn 或 hatenablog；想一起跑就设为 all。
