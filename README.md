# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                            |    Stmts |     Miss |   Cover |   Missing |
|---------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                     |      103 |       81 |     21% |31-33, 39-57, 62-101, 106-115, 120-143, 148-186 |
| custom\_components/roommind/config\_flow.py                     |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                            |       59 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py             |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py     |      186 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py          |      370 |       16 |     96% |375-376, 503, 548-559, 619 |
| custom\_components/roommind/control/mpc\_optimizer.py           |      157 |        7 |     96% |83, 114, 259, 264, 269, 277, 283 |
| custom\_components/roommind/control/residual\_heat.py           |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                    |       51 |        0 |    100% |           |
| custom\_components/roommind/control/thermal\_model.py           |      399 |       17 |     96% |358, 360, 612, 769-783, 946-950 |
| custom\_components/roommind/coordinator.py                      |      449 |       12 |     97% |188-189, 327, 383-384, 482-483, 612, 755-756, 760-761 |
| custom\_components/roommind/diagnostics.py                      |       40 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py            |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/mold\_manager.py           |       68 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_manager.py          |       92 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py        |       53 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py         |       31 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                          |       14 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                           |       52 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py            |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py      |      139 |        0 |    100% |           |
| custom\_components/roommind/store.py                            |       95 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py             |      129 |        1 |     99% |        92 |
| custom\_components/roommind/utils/mold\_utils.py                |       32 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py        |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py            |       21 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py            |      153 |        7 |     95% |133-134, 139-140, 148-149, 209 |
| custom\_components/roommind/utils/sensor\_utils.py              |       15 |        0 |    100% |           |
| custom\_components/roommind/utils/temp\_utils.py                |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                   |      190 |        0 |    100% |           |
| **TOTAL**                                                       | **3047** |  **152** | **95%** |           |


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