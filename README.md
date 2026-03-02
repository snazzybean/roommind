# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                |    Stmts |     Miss |   Cover |   Missing |
|---------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py         |      103 |       81 |     21% |31-33, 39-57, 62-101, 106-115, 120-143, 148-186 |
| custom\_components/roommind/analytics\_simulator.py |      143 |       18 |     87% |105-111, 122-129, 173-174, 196, 269-270 |
| custom\_components/roommind/config\_flow.py         |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                |       49 |        0 |    100% |           |
| custom\_components/roommind/coordinator.py          |      456 |      100 |     78% |29-31, 106, 128, 138-139, 145-187, 192-193, 198-203, 216-217, 236-237, 318-332, 393-396, 440-441, 477, 488-497, 510-518, 562-563, 584-585, 598-604, 623, 641-642, 653-660, 738, 742-747, 755-756, 797, 819-833, 842 |
| custom\_components/roommind/diagnostics.py          |       40 |       40 |      0% |     3-104 |
| custom\_components/roommind/history\_store.py       |      129 |       22 |     83% |90, 92, 94-105, 119-120, 139, 150, 168-169, 179-180 |
| custom\_components/roommind/mold\_utils.py          |       32 |        0 |    100% |           |
| custom\_components/roommind/mpc\_controller.py      |      234 |       44 |     81% |188, 198, 214-216, 253-254, 256-257, 276, 279-281, 288, 301, 306, 309, 315, 318-320, 360-365, 383, 398-411, 431, 438, 450, 455 |
| custom\_components/roommind/mpc\_optimizer.py       |      138 |        7 |     95% |69, 97, 202, 219, 224, 229, 237 |
| custom\_components/roommind/notification\_utils.py  |       50 |        3 |     94% |91, 119-120 |
| custom\_components/roommind/presence\_utils.py      |       17 |        1 |     94% |        21 |
| custom\_components/roommind/repairs.py              |       14 |       14 |      0% |      3-38 |
| custom\_components/roommind/schedule\_utils.py      |       89 |        1 |     99% |       119 |
| custom\_components/roommind/sensor.py               |       51 |       17 |     67% |32-44, 70-73, 97-100 |
| custom\_components/roommind/sensor\_utils.py        |       15 |        3 |     80% |     44-51 |
| custom\_components/roommind/solar.py                |       51 |        0 |    100% |           |
| custom\_components/roommind/store.py                |       68 |        1 |     99% |       115 |
| custom\_components/roommind/temp\_utils.py          |       26 |        0 |    100% |           |
| custom\_components/roommind/thermal\_model.py       |      372 |       27 |     93% |84, 112, 146, 180, 328, 333, 346, 350, 352, 374, 380, 416, 426-427, 437-438, 488, 598, 682, 723, 769-770, 851, 859, 890, 913-916 |
| custom\_components/roommind/websocket\_api.py       |      274 |       98 |     64% |61-66, 71-86, 304, 331-332, 342, 519-655, 741-750 |
| **TOTAL**                                           | **2362** |  **488** | **79%** |           |


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