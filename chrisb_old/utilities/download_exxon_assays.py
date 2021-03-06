# -*- coding: utf-8 -*-
'''
    script to download all the assays from Exxon's web site:
'''
import os
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

import requests
import lxml.html


main_url = ('http://corporate.exxonmobil.com/en/company/worldwide-operations/'
            'crude-oils/assays')


def main(destination):
    downloaded = {}

    # let's not use a static list of oils, but actually get the content from
    # the Exxon assays page.
    resp = requests.get(main_url)

    if resp.status_code != 200:
        print('Failed to download {} -- status code: {}'
              .format(main_url, resp.status_code))
        exit(1)

    htmltree = lxml.html.fromstring(resp.text)

    for li in htmltree.xpath("//ul[@class='downloads component']/li"):
        oil_name = li.xpath("a")[0].text
        oil_href = li.xpath("a")[0].get('href')

        if oil_href.endswith('.xlsx'):
            print (u'downloading: {}...'.format(oil_name))

            try:
                file_name = download_file(oil_href, destination)
                downloaded[oil_name] = file_name
            except IOError as e:
                print e

    create_index_file(downloaded, destination)


def download_file(oil_href, destination):
    # The Exxon website has some kind of limiter on downloads.
    # So it is possible that we have run this script multiple times, in which
    # a previous run successfully downloaded the file, but now it fails.
    #
    # We would like to make our download smart enough to check for the file
    # locally if we fail.  This will allow us to index the file if we are
    # reasonably confident that it exists and is useable.
    # - We don't clobber the local file outright.
    # - If we successfully downloaded the new file, use it, clobbering the
    #   old file, and report success.
    # - If we fail the download, but the old file exists, use the old file
    #   and report success.
    # - If we fail the download and the file does not exist, report a failure.
    #
    # We will communicate failure via an IOError.
    file_name = os.path.basename(oil_href)
    dest_file_name = os.path.join(destination, file_name)

    resp = requests.get(oil_href)

    if resp.status_code == 200:
        with open(dest_file_name, 'wb') as fd:
            fd.write(resp.content)
    elif (file_name in os.listdir(destination) and
          os.stat(dest_file_name).st_size > 0):
        # file exists and is non-zero length
        print ('\tFailed to download {}, status code: {}, use existing file'
               .format(dest_file_name, resp.status_code))
    else:
        raise IOError('\tFailed to download {}, status code: {}'
                      .format(dest_file_name, resp.status_code))

    return file_name


def create_index_file(downloaded, destination):
    # Create an index of our downloads as a .csv file.
    # The reason we would do this is because the name of the oil is not
    # actually contained in the spreadsheet content.  So we need a means of
    # remembering the name of the oil.
    index_file_name = os.path.join(destination, 'index.txt')

    with open(index_file_name, 'wb') as index_file:
        index_file.write('oil_name\tfile\n')

        for name, fname in sorted(downloaded.iteritems()):
            index_file.write('{}\t{}\n'.format(name, fname))


if __name__ == '__main__':
    parser = ArgumentParser(description='Exxon Assays Download Script.',
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-d', '--dest', metavar='<folder>', default='.',
                        dest='destination',
                        help='folder to use for saving downloaded files')

    args = parser.parse_args()

    print 'Saving Downloads to folder: {}'.format(args.destination)

    main(args.destination)
