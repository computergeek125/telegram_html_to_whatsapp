import argparse
from bs4 import BeautifulSoup
import pathlib
import pprint
import sys
import traceback
import zipfile

def transform_html_to_whatsapp(html_file, text_file):
    # Read the HTML file
    with open(html_file, 'r', encoding='utf-8') as file:
        html_content = file.read()

    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')

    # Extract chat messages
    messages = soup.find_all('div', class_='message')

    # Transform messages to WhatsApp format
    whatsapp_chat = ''
    m = 0
    for message in messages:
        try:
            sender_element = message.find('div', class_='from_name')
            if sender_element is None:
                continue  # Skip messages without sender information

            sender = sender_element.text.strip()
            timestamp_div = message.find('div', class_="pull_right date details")
            if timestamp_div:
                timestamp = timestamp_div['title']
                date_str = timestamp[:10]
                time_str = timestamp[11:19]
            else:
                date_str, time_str = None, None

            text_find = message.find('div', class_='text')
            if text_find is not None:
                text = text_find.text.strip()
            
            media_find = message.find('div', class_='media_wrap')
            media = []
            if media_find is not None:
                for media_link in media_find.find_all('a'):
                    if 'photo_wrap' in media_link.attrs:
                        media.append(media_link['href'])
                    elif 'video_wrap' in media_link.attrs:
                        media.append(media_link['href'])
                    else:
                        sys.stderr.write(f"WARN: Detected unknown media type in message #{m} ({date_str} {time_str}): {media_link.attrs}")
            # Format message in WhatsApp format
            if time_str:
                whatsapp_message = ''
                if text:
                    whatsapp_message += f'[{date_str}, {time_str}] {sender}: {text}\n'
                if media:
                    for media_item in media:
                        whatsapp_message += f'[{date_str}, {time_str}] {sender}: {media_item} (file attached)\n'
                whatsapp_chat += whatsapp_message
        except AttributeError as e:
            tbf = str(traceback.TracebackException.from_exception(e).format())
            sys.stderr.write(f"ERROR: Failed to parse message #{m} with traceback:{tbf}, source data follows:\n{message.prettify()}\n")
        m += 1

    # Save the transformed chat to a file
    with open(text_file, 'w', encoding='utf-8') as file:
        file.write(whatsapp_chat)

    print(f'Transformation complete. The WhatsApp chat export is saved as {text_file}')

# Usage example
#transform_html_to_whatsapp('messages.html')

def what_zip(text_file, name="Whatsapp Chat - person_name.zip"):
    with zipfile.ZipFile(pathlib.Path(text_file.parent, name), 'w') as zip_object:
        zip_object.write(text_file, arcname="_chat.txt")
        sys.stdout.write(f"ZIP file written to {zip_object.filename}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser_filedir = parser.add_mutually_exclusive_group()
    parser_filedir.add_argument("-f", "--file", help="Name of a singular file to parse")
    parser_filedir.add_argument("-d", "--dir",  help="Name of directory of files to parse - will parse every html in this folder")
    args = parser.parse_args()

    if args.file:
        input_file = pathlib.Path(args.file)
        output_file = pathlib.Path(input_file.parent, "_chat.txt")
        transform_html_to_whatsapp(input_file, output_file)
        what_zip(output_file)

    else:
        for input_file in pathlib.Path(args.dir).glob("*.html"):
            sys.stdout.write(f"Processing {input_file}...\n")
            output_file = input_file.with_suffix(".txt")
            transform_html_to_whatsapp(input_file, output_file)
            zip_int_name = input_file.with_suffix("").name
            zip_name = f"Whatsapp Chat - {zip_int_name}.zip"
            what_zip(output_file, name=zip_name)
