import argparse
from bs4 import BeautifulSoup
import datetime
import os
import pathlib
import pprint
import re
import sys
import traceback
import zipfile

def transform_html_to_whatsapp(html_file):
    # Read the HTML file
    with open(html_file, 'r', encoding='utf-8') as file:
        html_content = file.read()

    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract chat messages
    messages = soup.find_all('div', class_='message')

    # Transform messages to WhatsApp format
    whatsapp_chat = ''
    media_all = []
    media_dates = {}
    m = 0
    date_register = {}
    for message in messages:
        try:
            sender_element = message.find('div', class_='from_name')
            if sender_element is None:
                continue  # Skip messages without sender information

            sender = sender_element.text.strip()
            timestamp_div = message.find('div', class_="pull_right date details")
            if timestamp_div:
                timestamp = timestamp_div['title']
                real_date = datetime.datetime.strptime(timestamp, '%d.%m.%Y %H:%M:%S UTC%z')
                date_str = timestamp[:10]
                time_str = timestamp[11:19]
            else:
                real_date, date_str, time_str = None, None

            text_find = message.find('div', class_='text')
            if text_find is not None:
                text = text_find.text.strip()
            else:
                text = None
            
            media_find = message.find('div', class_='media_wrap')
            media_message = []
            if media_find is not None:
                for media_link in media_find.find_all('a'):
                    if 'photo_wrap' in media_link['class'] :
                        type_classifier = 'IMG'
                    elif 'video_file_wrap' in media_link['class']:
                        type_classifier = 'VID'
                    elif 'animated_wrap' in media_link['class']:
                        type_classifier = 'VID'
                    elif 'media' in media_link['class']:
                        type_classifier = 'DOC'
                    else:
                        sys.stderr.write(f"WARN: Detected unknown media type in message #{m} ({date_str} {time_str}): {media_link.attrs}\n")
                        type_classifier = None
                    if type_classifier:
                        filename = media_link['href']
                        filename_date = real_date.strftime('%Y%m%d')
                        filename_index = media_dates.get(filename_date, 0)
                        media_dates[filename_date] = filename_index+1
                        filename_ext = pathlib.Path(filename).suffix
                        new_filename = f"{type_classifier}-{filename_date}-WA{filename_index:04}{filename_ext}"
                        media_all.append((new_filename, filename))
                        media_message.append(new_filename)
            # Format message in WhatsApp format
            if time_str:
                whatsapp_message = ''
                if text:
                    whatsapp_message += f'[{date_str}, {time_str}] {sender}: {text}\n'
                if media_message:
                    for media_item in media_message:
                        whatsapp_message += f'[{date_str}, {time_str}] {sender}: {media_item[0]} (file attached)\n'
                whatsapp_chat += whatsapp_message
        except AttributeError:
            tbf = str(traceback.format_exc())
            sys.stderr.write(f"ERROR: Failed to parse message #{m} with traceback:\n{tbf}Source data follows:\n{message.prettify()}\n")
        m += 1
    rval = {"chat": whatsapp_chat, "media": media}
    return rval
    # Save the transformed chat to a file
    #with open(text_file, 'w', encoding='utf-8') as file:
    #    file.write(whatsapp_chat)

    #print(f'Transformation complete. The WhatsApp chat export is saved as {text_file}')

# Usage example
#transform_html_to_whatsapp('messages.html')

def what_zip(whatsapp_transform, base_path, name="Whatsapp Chat - person_name.zip"):
    bn = 0
    with zipfile.ZipFile(pathlib.Path(base_path.parent, name), 'w', compression=zipfile.ZIP_DEFLATED) as zip_object:
        sys.stdout.write(f"INFO: Exporting transform block {bn}\n")
        chat_agg = ""
        for block in whatsapp_transform:
            chat_agg += block["chat"]
            for file in block["media"]:
                sys.stdout.write(f"INFO: Adding {file[1]} as {file[0]}\n")
                try:
                    zip_object.write(filename=pathlib.Path(base_path, file[1]), arcname=file[0])
                except FileNotFoundError:
                    sys.stderr.write(f"WARN: Could not locate file {file[1]}, skipping")
        zip_object.writestr(zinfo_or_arcname="_chat.txt", data=chat_agg)
    sys.stdout.write(f"ZIP file written to {zip_object.filename}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser_filedir = parser.add_mutually_exclusive_group()
    parser_filedir.add_argument("-f", "--file", help="Name of a singular file to parse")
    parser_filedir.add_argument("-d", "--dir",  help="Name of directory of files to parse - will parse every html in this folder")
    args = parser.parse_args()

    if args.file:
        input_file = pathlib.Path(args.file)
        whatsapp_transform = transform_html_to_whatsapp(input_file)
        what_zip([whatsapp_transform], base_path=input_file.parent)

    else:
        whatsapp_transforms = []
        dir_path = pathlib.Path(args.dir)
        input_index = []
        num_re = re.compile(r'(\D+)?(\d+)?\.html')
        for input_file in dir_path.glob("*.html"):
            file_num = num_re.match(input_file.name).group(2)
            if file_num is None:
                file_num = 0
            else:
                file_num = int(file_num)
            input_index.append((input_file, file_num))
        print(input_index)
        input_index = sorted(input_index, key=lambda x: x[1])
        for index_entry in input_index:
            input_file = index_entry[0]
            sys.stdout.write(f"Processing {input_file}...\n")
            whatsapp_transforms.append(transform_html_to_whatsapp(input_file))

        zip_name = f"Whatsapp Chat - {dir_path.name}.zip"
        what_zip(whatsapp_transforms, name=zip_name, base_path=dir_path)
