# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      150 |       81 |     46% |41-43, 49-76, 99-100, 106-144, 149-160, 176-199, 230, 234-238, 244-245, 264-265 |
| custom\_components/roommind/binary\_sensor.py                      |       78 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      400 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      232 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      243 |        2 |     99% |   86, 119 |
| custom\_components/roommind/control/direct\_valve.py               |      115 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1605 |       49 |     97% |288, 334-335, 410-411, 417-418, 430-440, 854-856, 940-947, 986-988, 1250, 2105, 2345, 2348, 2460-2462, 2487-2489, 2491-2501, 2530, 2727-2729, 2821-2823, 2848-2850, 3473, 3475, 3486, 3488, 3493, 3498, 3520, 3522 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      427 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       48 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      574 |        2 |     99% | 531, 1345 |
| custom\_components/roommind/coordinator.py                         |     1769 |       33 |     98% |642-643, 1631-1632, 1642, 1644, 2297, 2358, 2387-2388, 2439, 2648, 2854-2857, 3462, 3471, 3493, 3499, 3501, 3507, 3661, 3666-3671, 3675, 3703, 3929, 3984-3985, 4000-4005, 4022-4023 |
| custom\_components/roommind/deprecation.py                         |       56 |        0 |    100% |           |
| custom\_components/roommind/diagnostics.py                         |      242 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      253 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_dry\_manager.py           |      206 |        0 |    100% |           |
| custom\_components/roommind/managers/air\_quality\_manager.py      |      148 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      261 |        3 |     99% |144, 307, 329 |
| custom\_components/roommind/managers/cover\_manager.py             |      227 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      302 |        1 |     99% |       218 |
| custom\_components/roommind/managers/device\_setpoint\_tracker.py  |      102 |        0 |    100% |           |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       71 |        0 |    100% |           |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       67 |        2 |     97% |    97, 99 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      126 |        2 |     98% |   69, 202 |
| custom\_components/roommind/managers/humidity\_manager.py          |       97 |        0 |    100% |           |
| custom\_components/roommind/managers/mold\_manager.py              |       86 |        0 |    100% |           |
| custom\_components/roommind/managers/price\_manager.py             |       87 |        0 |    100% |           |
| custom\_components/roommind/managers/recent\_temps.py              |       66 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |      202 |        4 |     98% |150, 153, 222-223 |
| custom\_components/roommind/managers/room\_fan\_manager.py         |       56 |        0 |    100% |           |
| custom\_components/roommind/managers/solar\_sensor\_manager.py     |      285 |        1 |     99% |       347 |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |       56 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      228 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_stats.py           |      205 |        4 |     98% |80, 109, 117, 159 |
| custom\_components/roommind/services/model\_backtest.py            |       77 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      184 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      114 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       36 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      201 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      186 |        2 |     99% |     98-99 |
| custom\_components/roommind/utils/mold\_utils.py                   |       34 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       76 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       49 |        0 |    100% |           |
| custom\_components/roommind/utils/price\_utils.py                  |      201 |        2 |     99% |   90, 176 |
| custom\_components/roommind/utils/schedule\_utils.py               |      279 |        3 |     99% |   419-421 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      409 |        3 |     99% |808, 1049-1054 |
| **TOTAL**                                                          | **11342** |  **207** | **98%** |           |


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