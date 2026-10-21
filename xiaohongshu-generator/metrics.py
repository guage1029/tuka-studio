"""Anonymous daily counters. No raw events or identities are stored."""
import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import sqlite3

from main import STYLE_NAMES
from safe_http import MESSAGES, RequestError

EVENTS = ('home_visit', 'app_visit', 'sample_view', 'template_select',
          'generation_start', 'generation_success', 'generation_failure', 'download_click')
CLIENT_EVENTS = {'sample_view', 'template_select', 'download_click'}
ERRORS = {'', *MESSAGES}
DEFAULT_DB = Path(__file__).resolve().parent / 'instance' / 'metrics.sqlite3'


def today():
    return datetime.now(timezone(timedelta(hours=8))).date()


def record(path, event, style='', error=''):
    if event not in EVENTS or (style and style not in STYLE_NAMES) or error not in ERRORS:
        raise RequestError('bad_request')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS counts (
            day TEXT NOT NULL, event TEXT NOT NULL, style TEXT NOT NULL, error TEXT NOT NULL,
            count INTEGER NOT NULL, PRIMARY KEY(day,event,style,error))''')
        day = today()
        db.execute('DELETE FROM counts WHERE day < ?', ((day - timedelta(days=89)).isoformat(),))
        db.execute('''INSERT INTO counts VALUES(?,?,?,?,1)
            ON CONFLICT(day,event,style,error) DO UPDATE SET count=count+1''',
                   (day.isoformat(), event, style, error))


def report(path):
    path = Path(path).resolve()
    if not path.exists():
        return '暂无统计数据。'
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT day,event,style,error,count FROM counts WHERE day>=? ORDER BY day,event',
                          ((today() - timedelta(days=89)).isoformat(),)).fetchall()
    lines = ['次数统计（非人数；下载点击不代表保存成功；日期为 UTC+8）', '日期         事件                     次数']
    daily, totals, popular, failures = {}, {}, {}, {}
    start = (today() - timedelta(days=6)).isoformat()
    for day, event, style, error, count in rows:
        daily[day, event] = daily.get((day, event), 0) + count
        if day >= start:
            totals[event] = totals.get(event, 0) + count
            if event == 'template_select' and style:
                popular[style] = popular.get(style, 0) + count
            if event == 'generation_failure':
                failures[error] = failures.get(error, 0) + count
    lines += [f'{day}   {event:24} {count}' for (day, event), count in sorted(daily.items())]
    lines += ['最近七天：'] + [f'  {event}: {totals.get(event, 0)}' for event in EVENTS]
    finished = totals.get('generation_success', 0) + totals.get('generation_failure', 0)
    lines += [f"已完成请求成功率: {totals.get('generation_success', 0) / finished:.1%}" if finished else '已完成请求成功率: 暂无数据',
              '热门模板（选择次数）: ' + ', '.join(f'{STYLE_NAMES[s]} {n}' for s, n in sorted(popular.items(), key=lambda row: -row[1])[:10]),
              '失败分类: ' + ', '.join(f'{error} {n}' for error, n in sorted(failures.items()))]
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='服务器本地只读匿名汇总统计')
    parser.add_argument('--db', default=os.environ.get('METRICS_DB', str(DEFAULT_DB)))
    print(report(parser.parse_args().db))
