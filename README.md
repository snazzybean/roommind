# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roomsense/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                 |    Stmts |     Miss |   Cover |   Missing |
|----------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roomsense/\_\_init\_\_.py         |       68 |       48 |     29% |29-31, 37-54, 59-68, 73-96, 101-139 |
| custom\_components/roomsense/analytics\_simulator.py |      143 |       18 |     87% |105-111, 122-129, 173-174, 196, 269-270 |
| custom\_components/roomsense/config\_flow.py         |       11 |       11 |      0% |      3-23 |
| custom\_components/roomsense/const.py                |       49 |        0 |    100% |           |
| custom\_components/roomsense/coordinator.py          |      445 |      100 |     78% |28-30, 103, 125, 135-136, 142-184, 189-190, 195-200, 213-214, 231, 312-326, 386-389, 433-434, 443-444, 472, 483-492, 505-513, 557-558, 579-580, 593-599, 618, 636-637, 648-655, 733, 737-742, 750-751, 792, 814-828 |
| custom\_components/roomsense/diagnostics.py          |       40 |       40 |      0% |     3-104 |
| custom\_components/roomsense/history\_store.py       |      129 |       22 |     83% |90, 92, 94-105, 119-120, 139, 150, 168-169, 179-180 |
| custom\_components/roomsense/mold\_utils.py          |       32 |        0 |    100% |           |
| custom\_components/roomsense/mpc\_controller.py      |      220 |       41 |     81% |187, 197, 213-215, 252-253, 255-256, 275, 278-280, 287, 300, 305, 308, 314, 317-319, 359-364, 382, 397-409, 428, 434 |
| custom\_components/roomsense/mpc\_optimizer.py       |      138 |        7 |     95% |69, 97, 202, 219, 224, 229, 237 |
| custom\_components/roomsense/notification\_utils.py  |       50 |        3 |     94% |91, 119-120 |
| custom\_components/roomsense/presence\_utils.py      |       17 |        1 |     94% |        21 |
| custom\_components/roomsense/repairs.py              |       14 |       14 |      0% |      3-38 |
| custom\_components/roomsense/schedule\_utils.py      |       83 |        1 |     99% |       117 |
| custom\_components/roomsense/sensor.py               |       51 |       17 |     67% |32-44, 70-73, 97-100 |
| custom\_components/roomsense/sensor\_utils.py        |       15 |        3 |     80% |     44-51 |
| custom\_components/roomsense/solar.py                |       51 |        0 |    100% |           |
| custom\_components/roomsense/store.py                |       68 |        1 |     99% |       115 |
| custom\_components/roomsense/thermal\_model.py       |      372 |       27 |     93% |84, 112, 146, 180, 328, 333, 346, 350, 352, 374, 380, 416, 426-427, 437-438, 488, 598, 682, 723, 769-770, 851, 859, 890, 913-916 |
| custom\_components/roomsense/websocket\_api.py       |      271 |       98 |     64% |61-66, 71-86, 304, 331-332, 342, 514-650, 736-745 |
| **TOTAL**                                            | **2267** |  **452** | **80%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/snazzybean/roomsense/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/snazzybean/roomsense/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/snazzybean/roomsense/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/snazzybean/roomsense/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fsnazzybean%2Froomsense%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/snazzybean/roomsense/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.