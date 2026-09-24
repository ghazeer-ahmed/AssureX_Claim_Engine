import csv
import json
import random
from collections import Counter
from pathlib import Path


root = Path(__file__).resolve().parent.parent
data_dir = root / 'data'
full_file = data_dir / 'claims_full.csv'


def save_rows(path, rows, cols):
    with open(path, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)


def main():
    with open(full_file, newline='', encoding='utf-8-sig') as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise ValueError('claims_full.csv is empty.')

    cols = list(rows[0].keys())
    if not {'claim_id', 'claim_class'}.issubset(cols):
        raise ValueError('claims_full.csv needs claim_id and claim_class columns.')

    ids = [row['claim_id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Each claim_id must be unique.')

    groups = {}
    for row in rows:
        groups.setdefault(row['claim_class'], []).append(row)

    rng = random.Random(42)
    split_rows = {'train': [], 'validation': [], 'test': []}
    split_map = []

    for label, items in groups.items():
        rng.shuffle(items)
        total = len(items)
        train_end = total * 70 // 100
        validation_end = train_end + total * 15 // 100
        if total - validation_end != total * 15 // 100:
            raise ValueError('Each class must split exactly into 70, 15 and 15 percent.')

        parts = {
            'train': items[:train_end],
            'validation': items[train_end:validation_end],
            'test': items[validation_end:]
        }
        for split, part in parts.items():
            split_rows[split].extend(part)
            for row in part:
                split_map.append({
                    'claim_id': row['claim_id'],
                    'split': split,
                    'claim_class': label
                })

    for split, items in split_rows.items():
        items.sort(key=lambda row: row['claim_id'])
        save_rows(data_dir / ('claims_' + split + '.csv'), items, cols)

    split_map.sort(key=lambda row: row['claim_id'])
    save_rows(data_dir / 'claim_split_map.csv', split_map, ['claim_id', 'split', 'claim_class'])

    stats = {'seed': 42, 'splits': {}}
    for split, items in split_rows.items():
        stats['splits'][split] = {
            'total': len(items),
            'class_counts': dict(Counter(row['claim_class'] for row in items))
        }
    stats['full'] = {
        'total': len(rows),
        'class_counts': dict(Counter(row['claim_class'] for row in rows))
    }
    with open(data_dir / 'dataset_statistics.json', 'w', encoding='utf-8') as file:
        json.dump(stats, file, indent=2)

    print('split complete')
    for split, items in split_rows.items():
        print(split + ':', len(items))


if __name__ == '__main__':
    main()
