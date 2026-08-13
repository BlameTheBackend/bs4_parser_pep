import re
import logging
from urllib.parse import urljoin
from collections import Counter

import requests_cache
from tqdm import tqdm

from configs import configure_argument_parser, configure_logging
from constants import BASE_DIR, MAIN_DOC_URL, PEP_DOC_URL, EXPECTED_STATUS
from exceptions import EmptyListException
from outputs import control_output
from utils import get_soup, find_tag


def whats_new(session):
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    whats_new_url = urljoin(MAIN_DOC_URL, 'whatsnew/')
    session = requests_cache.CachedSession()
    soup = get_soup(session, whats_new_url)
    if soup is None:
        return
    main_div = find_tag(soup, 'section', attrs={'id': 'what-s-new-in-python'})
    div_with_ul = find_tag(main_div, 'div', attrs={'class': 'toctree-wrapper'})
    sections_by_python = div_with_ul.find_all(
        'li', attrs={'class': 'toctree-l1'}
    )
    for section in tqdm(sections_by_python, colour='green'):
        version_a_tag = find_tag(section, 'a')
        version_link = urljoin(whats_new_url, version_a_tag['href'])
        soup = get_soup(session, version_link)
        if soup is None:
            continue
        h1 = find_tag(soup, 'h1')
        dl = find_tag(soup, 'dl')
        dl_text = dl.text.replace('\n', ' ')
        results.append(
            (version_link, h1.text, dl_text)
        )
    return results


def latest_versions(session):
    results = [('Ссылка на статью', 'Заголовок', 'Редактор, автор')]
    session = requests_cache.CachedSession()
    soup = get_soup(session, MAIN_DOC_URL)
    if soup is None:
        return
    sidebar = find_tag(soup, 'div', {'class': 'sphinxsidebarwrapper'})
    ul_tags = sidebar.find_all('ul')
    for ul in ul_tags:
        if 'All versions' in ul.text:
            a_tags = ul.find_all('a')
            break
    else:
        raise EmptyListException('Не найден список c версиями Python')

    pattern = r'Python (?P<version>\d\.\d+) \((?P<status>.*)\)'
    for a_tag in a_tags:
        link = a_tag['href']
        text_match = re.search(pattern, a_tag.text)
        if text_match is not None:
            version, status = text_match.groups()
        else:
            version, status = a_tag.text, ''
        results.append(
            (link, version, status)
        )
    return results


def download(session):
    downloads_url = urljoin(MAIN_DOC_URL, 'download.html')
    session = requests_cache.CachedSession()
    soup = get_soup(session, downloads_url)
    if soup is None:
        return
    main_tag = find_tag(soup, 'div', {'role': 'main'})
    table_tag = find_tag(main_tag, 'table', {'class': 'docutils'})
    html_tag = find_tag(table_tag, 'a', {'href': re.compile(r'.+html\.zip$')})
    html_link = html_tag['href']
    archive_url = urljoin(downloads_url, html_link)
    filename = archive_url.split('/')[-1]
    downloads_dir = BASE_DIR / 'downloads'
    downloads_dir.mkdir(exist_ok=True)
    archive_path = downloads_dir / filename
    response = session.get(archive_url)

    with open(archive_path, 'wb') as file:
        file.write(response.content)


def pep(session):
    results = [('Статус', 'Количество')]
    session = requests_cache.CachedSession()
    soup = get_soup(session, PEP_DOC_URL)
    if soup is None:
        return
    tables = soup.find_all('table', {'class': 'pep-zero-table'})
    table_bodies = [find_tag(table, 'tbody') for table in tables]
    quantity = 0
    quantity_status = Counter()
    mismatched_statuses = []
    for body in tqdm(table_bodies):
        for tr in body.find_all('tr'):
            td_tags = tr.find_all('td')
            abbr = td_tags[0].find('abbr')
            status_symbols = abbr.text if abbr else ''
            status_symbols = status_symbols[1:]
            pep_status = EXPECTED_STATUS[status_symbols]
            href = find_tag(td_tags[1], 'a')['href']
            link = urljoin(PEP_DOC_URL, href)

            session = requests_cache.CachedSession()
            soup = get_soup(session, link)
            if soup is None:
                continue
            dl_tag = find_tag(soup, 'dl', {'class': 'field-list'})
            dt_status = dl_tag.find(
                lambda tag: tag.name == 'dt'
                and tag.get_text(strip=True) == 'Status:')
            child_status = dt_status.find_next_sibling().find('abbr').text
            if child_status not in pep_status:
                mismatched_statuses.append((link, child_status, pep_status))
            quantity += 1
            quantity_status[child_status] += 1
    if len(mismatched_statuses) > 0:
        logging.info('Несовпадающие статусы:')
        for status in mismatched_statuses:
            logging.info(status[0])
            logging.info(f'Статус в карточке: {status[1]}')
            logging.info(f'Ожидаемые статусы: {status[2]}')
    results.extend(quantity_status.items())
    return results


MODE_TO_FUNCTION = {
    'whats-new': whats_new,
    'latest-versions': latest_versions,
    'download': download,
    'pep': pep,
}


def main():
    configure_logging()
    logging.info('Парсер запущен!')

    arg_parser = configure_argument_parser(MODE_TO_FUNCTION.keys())
    args = arg_parser.parse_args()
    logging.info(f'Аргументы командной строки: {args}')

    session = requests_cache.CachedSession()
    if args.clear_cache:
        session.cache.clear()

    parser_mode = args.mode
    results = MODE_TO_FUNCTION[parser_mode](session)

    if results is not None:
        control_output(results, args)
    logging.info('Парсер завершил работу.')


if __name__ == '__main__':
    main()
