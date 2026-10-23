"""Reproduce a fixed, source-only inspection; emits texts, never factor values."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request-sha256', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    request_path = root / 'experiments/qlib/cash-profitability-two-report-source-request.json'
    if digest(request_path) != args.request_sha256:
        raise ValueError('frozen source request changed')
    request = json.loads(request_path.read_text())
    if request['status'] != 'FROZEN_SOURCE_INSPECTION_ONLY' or request['strategy_registered'] is not False:
        raise ValueError('source-only request required')
    paths = {}
    for key in request['input_sha256']:
        prefix, relative = key.split('/', 1)
        base = {'repo': root, 'source': args.source_root}[prefix].resolve()
        path = (base / relative).resolve()
        if not path.is_relative_to(base):
            raise ValueError('input escaped fixed root')
        paths[key] = path
    expected = {**request['input_sha256'], 'frozen_request': args.request_sha256}
    paths['frozen_request'] = request_path

    def verify_inputs():
        actual = {key: digest(path) for key, path in paths.items()}
        if actual != expected:
            raise ValueError('source or method changed')
        return actual

    verify_inputs()
    import pypdf
    import pdfminer
    from pdfminer.high_level import extract_text
    if pypdf.__version__ != '6.10.0' or pdfminer.__version__ != '20251230':
        raise ValueError('frozen reader versions required')
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / 'input-before.json', expected)
    try:
        summaries = []
        for case in request['documents']:
            source = paths[case['input_key']]
            directory = args.output / source.stem
            directory.mkdir()
            reader = pypdf.PdfReader(source)
            texts = []
            labels = {label: [] for label in request['labels']}
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ''
                texts.append(text)
                (directory / f'pypdf-page-{number}.txt').write_text(text)
                compact = ''.join(text.split())
                for label in labels:
                    if label in compact:
                        labels[label].append(number)
            for number in case['independent_reader_physical_pages']:
                if number < 1 or number > len(texts):
                    raise ValueError('fixed physical page outside source')
                alternate = extract_text(str(source), page_numbers=[number - 1])
                (directory / f'pdfminer-page-{number}.txt').write_text(alternate)
            summaries.append({
                'source_input_key': case['input_key'], 'published_day': case['published_day'],
                'source_sha256': digest(source), 'physical_pages': len(texts),
                'pypdf_page_text_sha256': {str(i+1): hashlib.sha256(t.encode()).hexdigest() for i,t in enumerate(texts)},
                'label_physical_page_index': labels,
                'independent_reader_physical_pages': case['independent_reader_physical_pages'],
            })
        manifest = {'status': 'SOURCE_TEXT_INSPECTION_ONLY', 'request_sha256': args.request_sha256,
                    'documents': summaries, 'numeric_factor_computed': False, 'ranking_computed': False,
                    'portfolio_return_computed': False, 'historical_arrival_verified': False,
                    'strategy_registered': False, 'objective_achieved': False}
        manifest['input_after_sha256'] = verify_inputs()
        manifest['all_inputs_unchanged'] = True
        manifest['output_sha256'] = {str(p.relative_to(args.output)): digest(p)
                                     for p in sorted(args.output.rglob('*')) if p.is_file()}
        write(args.output / 'manifest.json', manifest)
        print(json.dumps({'status': manifest['status'], 'documents': len(summaries),
                          'output_files': len(manifest['output_sha256']) + 1,
                          'all_inputs_unchanged': True}))
    except Exception as error:
        write(args.output / 'failure.json', {'error': repr(error), 'portfolio_return_computed': False})
        raise


if __name__ == '__main__':
    main()
