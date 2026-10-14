"""Offline import of an official IDE library export; never publishes device DPs."""
from dataclasses import asdict
import hashlib
import json
from .rgbic_scene_protocol import decode_scene_hex, encode_scene_hex

PID = 'example-product-led'
API = 'tuya.m.light.panel.library.data.get'
GROUPS = ('DIY', 'Scenery', 'Life', 'Festival', 'Mood')


def import_library(raw: bytes):
    if type(raw) is not bytes or len(raw) > 5_000_000:
        raise ValueError('Invalid library input size')
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Invalid library JSON') from None
    if not isinstance(doc, dict) or doc.get('format') != 'smart-tray-tuya-library-v1':
        raise ValueError('Official IDE export envelope required')
    if doc.get('status') != 'read_ok' or doc.get('source_api') != API or doc.get('source_version') != '1.0':
        raise ValueError('Successful official library export required')
    if doc.get('product_id') != PID or doc.get('device_id_masked') != 'exampl…0001':
        raise ValueError('Product/device mismatch')
    if doc.get('binding_evidence') != 'official_ide_context_matches_cached_cloud_metadata':
        raise ValueError('Missing binding evidence')
    plates = doc.get('result')
    if not isinstance(plates, list) or len(plates) > 1000:
        raise ValueError('Invalid library result')
    scenes, rejected, seen = [], [], set()
    counts = dict.fromkeys(GROUPS, 0)
    counts['Unclassified'] = 0
    total = 0
    for plate in plates:
        if not isinstance(plate, dict) or not isinstance(plate.get('data'), list):
            raise ValueError('Invalid category shape')
        category = plate.get('plateName')
        source_category = category if isinstance(category, str) and len(category) <= 120 and category.isprintable() else None
        category = category if isinstance(category, str) and category in GROUPS else 'Unclassified'
        for group in plate['data']:
            if not isinstance(group, dict) or not isinstance(group.get('items'), list):
                raise ValueError('Invalid group shape')
            for item in group['items']:
                total += 1
                if total > 10000:
                    raise ValueError('Too many scenes')
                try:
                    if not isinstance(item, dict):
                        raise ValueError('invalid_scene')
                    name, payload = item.get('sceneName'), item.get('sceneData')
                    scene_id, dp_id = item.get('sceneId'), item.get('dpId')
                    if not isinstance(name, str) or not name.strip() or len(name) > 120 or not all(c.isprintable() for c in name):
                        raise ValueError('invalid_name')
                    if item.get('dpCode') != 'dreamlight_scene_mode' or type(dp_id) is not int or dp_id != 51:
                        raise ValueError('dp_mismatch')
                    if type(scene_id) is not int or not 0 <= scene_id <= 2**53-1:
                        raise ValueError('invalid_scene_id')
                    frame = decode_scene_hex(payload)
                    if encode_scene_hex(frame) != payload.lower():
                        raise ValueError('roundtrip_mismatch')
                    fingerprint = (category, scene_id, payload.lower())
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    scenes.append({'name': name, 'category': category, 'source_category': source_category, 'library_scene_id': scene_id,
                        'dp_id_declared': dp_id, 'dp_code': item['dpCode'], 'payload_hex': payload,
                        'payload_bytes': len(payload)//2, 'decoded': asdict(frame),
                        'source_plate_id': plate.get('plateId') if type(plate.get('plateId')) is int else None,
                        'codec_roundtrip_ok': True, 'product_binding': 'export_context_only_not_independently_verified',
                        'lan_encoding_confirmed': False, 'write_validated': False})
                    counts[category] += 1
                except (ValueError, TypeError, AttributeError):
                    # Do not copy rejected fields or exception text into reports.
                    rejected.append({'item_index': total, 'reason': 'invalid_or_unsupported_scene'})
    return {'product_id': PID, 'source_api': API, 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'source_kind': 'official_ide_export_claim_not_cryptographic_attestation',
        'scene_count': len(scenes), 'category_counts': counts, 'scenes': scenes,
        'rejected_count': len(rejected), 'rejected': rejected,
        'neon_world_found': any(s['name'].casefold() == 'neon world' for s in scenes),
        'replay_ready': False, 'writes_sent': 0}
