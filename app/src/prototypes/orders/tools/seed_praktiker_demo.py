#!/usr/bin/env python3
"""Create the commissioned synthetic Praktiker order, once, with a real file attachment.

Run against the preview's Sample Hardware company store only. This never queues email or calls providers.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customer_details
import order_files
import quote
import spec
from store import CompanyStore


def seed(database, configuration):
    store = CompanyStore(database)
    try:
        company = store.one('SELECT id FROM company')
        if not company or company['id'] != 'sample-hardware' or configuration.get('slug') != 'sample-hardware':
            raise ValueError('Choose the Sample Hardware demo store.')
        existing = store.one("SELECT o.id FROM orders o JOIN customers c ON c.id=o.customer_id "
                             "WHERE json_extract(c.data,'$.demo_scenario')='praktiker' AND json_extract(c.data,'$.is_demo')=1 LIMIT 1")
        if existing:
            return {'id': existing['id'], 'created': False}
        catalogue = store.export_catalog()
        scenario = spec.demo_order(catalogue, configuration)
        lines = scenario['lines']
        text = '\n'.join(line['source'] for line in lines)
        body = io.BytesIO()
        with zipfile.ZipFile(body, 'w', zipfile.ZIP_DEFLATED) as document:
            def part(name, content):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                document.writestr(info, content)

            part('[Content_Types].xml',
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>')
            part('_rels/.rels',
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '</Relationships>')
            paragraphs = ['Praktiker DEMO-PRA-2026-001', *[line['source'] for line in lines]]
            part('word/document.xml',
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
                ''.join('<w:p><w:r><w:t>' + escape(text) + '</w:t></w:r></w:p>' for text in paragraphs) +
                '<w:sectPr/></w:body></w:document>')
        uploaded = order_files.stage(store, 'Praktiker-DEMO-PRA-2026-001.docx', body.getvalue(),
                                     'praktiker-demo-upload-v2')
        customer = dict(scenario['demo_order']['customer'], kind='company', warehouseConfirmed='yes',
                        specification=text, specification_file=uploaded['id'],
                        notes='Демонстрационна поръчка. Фирмените и фактурните данни са примерни.')
        customer['capture'] = {'schema': 'rocoto.orders.capture.v1', 'entry_path': 'specification',
            'language': 'bg', 'specification': {'text': text, 'file_id': uploaded['id'], 'lines': [
                {'source': line['source'], 'quantity': line['qty'], 'selected_code': line['matches'][0],
                 'status': 'exact'} for line in lines]}}
        customer = customer_details.validate(customer, configuration)
        customer.update(is_demo=True, demo_scenario='praktiker')
        priced = quote.quote(catalogue, [{'code': line['matches'][0], 'rows': [{'x': 0, 'n': line['qty']}]} for line in lines])
        priced['quote']['fulfilment'] = 'pickup'
        result = store.submit_order(customer, priced['lines'], priced['quote'], 'praktiker-demo-order-v1',
                                    'demo-seed', 'Peter-approved synthetic Praktiker demonstration')
        return {'id': result['id'], 'created': True}
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--configuration', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(seed(args.database, json.loads(args.configuration.read_text()))))
