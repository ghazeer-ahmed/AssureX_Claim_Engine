import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


root = Path(__file__).resolve().parent.parent
data_dir = root / 'data'
cards_dir = root / 'cards'


def card_name(label):
    return label.lower().replace(' ', '_')


def text_font(size):
    try:
        return ImageFont.truetype('arial.ttf', size)
    except OSError:
        return ImageFont.load_default()


def draw_card(row, path, version):
    if version == 1:
        back = 'white'
        bar = (32, 72, 125)
    else:
        back = (242, 244, 247)
        bar = (63, 81, 97)

    image = Image.new('RGB', (1000, 760), back)
    draw = ImageDraw.Draw(image)
    title = text_font(34 if version == 1 else 30)
    head = text_font(22 if version == 1 else 20)
    body = text_font(19 if version == 1 else 18)

    draw.rectangle((0, 0, 1000, 90), fill=bar)
    draw.text((35, 25), 'ASSUREX CLAIM SUMMARY CARD', fill='white', font=title)
    draw.text((35, 115), 'Claim ID: ' + row['claim_id'], fill=bar, font=head)

    data = [
        ('Product category', row['product_category']),
        ('Brand', row['brand']),
        ('Product age days', row['product_age_days']),
        ('Warranty status', row['warranty_status']),
        ('Remaining warranty days', row['remaining_warranty_days']),
        ('Fault category', row['fault_category']),
        ('Damage type', row['damage_type']),
        ('Previous repairs', row['previous_repairs']),
        ('Receipt available', 'Yes' if row['receipt_uploaded'] == '1' else 'No'),
        ('Warranty card available', 'Yes' if row['warranty_card_uploaded'] == '1' else 'No'),
        ('Product image available', 'Yes' if row['product_image_uploaded'] == '1' else 'No'),
        ('Serial evidence available', 'Yes' if row['serial_evidence_uploaded'] == '1' else 'No'),
        ('Serial match', 'Yes' if row['serial_match'] == '1' else 'No'),
        ('Fault evidence available', 'Yes' if row['fault_evidence_uploaded'] == '1' else 'No'),
        ('Missing documents', row['missing_documents']),
        ('Duplicate claim', 'Yes' if row['duplicate_claim_flag'] == '1' else 'No'),
        ('Contradictions', row['contradiction_count']),
        ('Reporting delay days', row['reporting_delay_days'])
    ]

    y = 165
    for index, item in enumerate(data):
        if index and index % 2 == 0:
            y += 50
        x = 35 if index % 2 == 0 else 525
        draw.text((x, y), item[0] + ': ' + str(item[1]), fill=(32, 45, 60), font=body)

    draw.line((35, 690, 965, 690), fill=(190, 198, 207), width=2)
    draw.text((35, 712), 'Claim facts only', fill=(80, 92, 105), font=body)
    image.save(path, format='PNG')


def main():
    with open(data_dir / 'claims_full.csv', newline='', encoding='utf-8-sig') as file:
        rows = {row['claim_id']: row for row in csv.DictReader(file)}
    with open(data_dir / 'claim_split_map.csv', newline='', encoding='utf-8-sig') as file:
        split_map = list(csv.DictReader(file))

    manifest = []
    folders = {
        'train': 'gtm_training',
        'validation': 'holdout_validation',
        'test': 'holdout_test'
    }
    for item in split_map:
        claim = rows[item['claim_id']]
        folder = cards_dir / folders[item['split']] / card_name(item['claim_class'])
        folder.mkdir(parents=True, exist_ok=True)
        versions = [1, 2] if item['split'] == 'train' else [1]

        for version in versions:
            name = item['claim_id'] + '_v' + str(version) + '.png'
            path = folder / name
            if not path.is_file():
                draw_card(claim, path, version)
            manifest.append({
                'claim_id': item['claim_id'],
                'claim_class': item['claim_class'],
                'split': item['split'],
                'variation': 'v' + str(version),
                'path': str(path.relative_to(cards_dir)).replace('\\', '/')
            })

    with open(cards_dir / 'card_manifest.csv', 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['claim_id', 'claim_class', 'split', 'variation', 'path'])
        writer.writeheader()
        writer.writerows(manifest)

    summary = {
        'total_images': len(manifest),
        'training_images': sum(1 for item in manifest if item['split'] == 'train'),
        'validation_images': sum(1 for item in manifest if item['split'] == 'validation'),
        'test_images': sum(1 for item in manifest if item['split'] == 'test')
    }
    with open(cards_dir / 'card_summary.json', 'w', encoding='utf-8') as file:
        json.dump(summary, file, indent=2)
    print('cards complete:', len(manifest))


if __name__ == '__main__':
    main()
