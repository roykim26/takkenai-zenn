# 简短日志排查清单

## 1. 先搜：`publish run start`

确认今天有没有启动过自动任务。

## 2. 再搜：`publish run end`

确认这次运行有没有正常结束。

## 3. 看结果码

搜：`main.py exit code=`

或看结尾的：`exit=`

- `0` = 程序正常结束
- `1` 或其他数字 = 本次执行失败

## 4. 看目录对不对

搜：`project_dir=`

应该是项目实际目录：

```text
E:\yanque\海外投放\zenn-bot
```

## 5. 看 Python 是否正常

搜：`python_version:`

后面应该能看到 Python 版本号。

## 6. 看有没有真正进入主程序

搜：`main.py output:`

后面应该有主程序日志。

## 7. 看今天有没有可处理记录

搜：`今日可检查记录数`

- 如果是 `0`，说明今天没有符合条件的记录
- 如果大于 `0`，再继续看后面的跳过或失败原因

## 8. 如果今天没发文章

重点看 `main.py output:` 后面有没有这些词：

- `没有可检查记录`
- `跳过`
- `queued`
- `waiting`
- `配额保护`
- `发布失败`
- `检测到已有发布任务`

## 9. 如果提示已有任务在运行

重点一起看：

- `lock_state_before`
- `visible_python_processes_before`
- `lock_state_after`
- `visible_python_processes_after`

## 注意

不要只看 `.publish.lock` 文件里写的是 `done` 还是 `running`。

真正是否被锁住，要结合锁文件状态和 Python 进程一起判断。
