# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                |    Stmts |     Miss |   Cover |   Missing |
|---------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py         |      103 |       81 |     21% |31-33, 39-57, 62-101, 106-115, 120-143, 148-186 |
| custom\_components/roommind/analytics\_simulator.py |      186 |       27 |     85% |111-123, 140-147, 202-203, 210-211, 229, 249, 271-272, 327-328, 364-365, 379-380 |
| custom\_components/roommind/config\_flow.py         |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                |       59 |        0 |    100% |           |
| custom\_components/roommind/coordinator.py          |      619 |       87 |     86% |29-31, 110, 132, 142-143, 152, 176-191, 196-197, 202-207, 220-221, 240-241, 322-336, 367-373, 430, 435, 446-449, 507-509, 519-520, 614-622, 719-720, 735-736, 787-788, 840, 874, 876-879, 967, 971, 978-990, 996-997, 1043 |
| custom\_components/roommind/diagnostics.py          |       40 |        0 |    100% |           |
| custom\_components/roommind/history\_store.py       |      129 |        2 |     98% |   92, 139 |
| custom\_components/roommind/mold\_utils.py          |       32 |        0 |    100% |           |
| custom\_components/roommind/mpc\_controller.py      |      370 |       16 |     96% |375-376, 503, 548-559, 619 |
| custom\_components/roommind/mpc\_optimizer.py       |      157 |        7 |     96% |83, 114, 259, 264, 269, 277, 283 |
| custom\_components/roommind/notification\_utils.py  |       50 |        3 |     94% |91, 119-120 |
| custom\_components/roommind/presence\_utils.py      |       21 |        2 |     90% |    21, 42 |
| custom\_components/roommind/repairs.py              |       14 |        0 |    100% |           |
| custom\_components/roommind/residual\_heat.py       |       24 |        1 |     96% |        51 |
| custom\_components/roommind/schedule\_utils.py      |      153 |        7 |     95% |133-134, 139-140, 148-149, 209 |
| custom\_components/roommind/sensor.py               |       51 |        0 |    100% |           |
| custom\_components/roommind/sensor\_utils.py        |       15 |        3 |     80% |     44-51 |
| custom\_components/roommind/solar.py                |       51 |        0 |    100% |           |
| custom\_components/roommind/store.py                |       95 |        3 |     97% |117, 119, 160 |
| custom\_components/roommind/temp\_utils.py          |       26 |        0 |    100% |           |
| custom\_components/roommind/thermal\_model.py       |      380 |       25 |     93% |86, 116, 152, 188, 336, 341, 354, 358, 360, 383, 425, 435-436, 446-447, 499, 612, 700, 741, 787-788, 871, 910, 933-936 |
| custom\_components/roommind/websocket\_api.py       |      312 |       32 |     90% |310, 316, 335, 362-363, 373, 552-553, 557, 559, 672-674, 689-691, 693-715 |
| **TOTAL**                                           | **2898** |  **307** | **89%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/snazzybean/roommind/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/snazzybean/roommind/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fsnazzybean%2Froommind%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.