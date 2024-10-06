import argparse
from collections import namedtuple
import datetime
import logging
import pathlib
import re
import zipfile

from bs4 import BeautifulSoup

LOG_TRACE = False

WhatsappMessageStruct = namedtuple(
    "WAMS",
    [
        "telegram_id",
        "real_date",
        "date_str",
        "time_str",
        "sender",
        "text",
        "media_message",
    ],
)


def transform_html_to_whatsapp(html_file, logger: logging.Logger):
    """Converts an HTML file from Telegram into a representation of WhatsApp `_chat.txt` format

    Args:
        html_file (file): HTML file to read

    Returns:
        dict: Dictionary representing the WhatsApp chat and references to the media
    """
    # Read the HTML file
    with open(html_file, "r", encoding="utf-8") as file:
        html_content = file.read()

    # Parse the HTML content
    soup = BeautifulSoup(html_content, "html.parser")

    # Extract chat messages
    messages = soup.find_all("div", class_="message")

    # Transform messages to WhatsApp format
    whatsapp_buffer = []
    media_all = []
    media_dates = {}
    m = 0
    for message in messages:
        try:
            if message["id"].startswith("message"):
                telegram_id = int(message["id"][7:])
            else:
                telegram_id = None
                logger.warning(
                    "Failed to parse message #%i telegram ID from data:\n%s",
                    m,
                    message.prettify(),
                )
            if telegram_id == -1:
                logger.debug("Skipping telegram ID#-1")
                if LOG_TRACE:
                    logger.debug("Message %i ID#-1 data:\n%s", m, message.prettify())
                continue
            sender = None
            if "joined" in message["class"] and m > 0:
                last_msg = whatsapp_buffer[-1]
                real_date = last_msg.real_date
                date_str = last_msg.date_str
                time_str = last_msg.time_str
                sender = last_msg.sender
            else:
                sender_element = message.find("div", class_="from_name")
                sender = sender_element.text.strip()
                timestamp_div = message.find("div", class_="pull_right date details")
                if timestamp_div:
                    timestamp = timestamp_div["title"]
                    real_date = datetime.datetime.strptime(
                        timestamp, "%d.%m.%Y %H:%M:%S UTC%z"
                    )
                    date_str = timestamp[:10]
                    time_str = timestamp[11:19]
                else:
                    real_date, date_str, time_str = None, None, None

            if sender is None:
                logger.warning(
                    "Message #%i (ID#%i): found orphaned data:\n%s",
                    m,
                    telegram_id,
                    message.prettify(),
                )
                continue  # Skip messages without sender information

            text_find = message.find("div", class_="text")
            if text_find is not None:
                if LOG_TRACE:
                    logger.debug(
                        "Message #%i (ID#%i): found data:\n%s",
                        m,
                        telegram_id,
                        text_find.prettify(),
                    )
                text = text_find.text.strip()
            else:
                text = None

            media_find = message.find("div", class_="media_wrap")
            media_message = []
            if media_find is not None:
                if LOG_TRACE:
                    logger.debug(
                        "Message #%i (ID#%i): found media data:\n%s",
                        m,
                        telegram_id,
                        media_find.prettify(),
                    )
                for media_link in media_find.find_all("a"):
                    if "photo_wrap" in media_link["class"]:
                        type_classifier = "IMG"
                    elif "video_file_wrap" in media_link["class"]:
                        type_classifier = "VID"
                    elif "animated_wrap" in media_link["class"]:
                        type_classifier = "VID"
                    elif "media" in media_link["class"]:
                        type_classifier = "DOC"
                    else:
                        logger.warning(
                            "Detected unknown media type in message #%i (ID#%i) (%s %s): %s",
                            m,
                            telegram_id,
                            date_str,
                            time_str,
                            media_link.attrs,
                        )
                        type_classifier = None
                    if type_classifier:
                        filename = media_link["href"]
                        filename_date = real_date.strftime("%Y%m%d")
                        filename_index = media_dates.get(filename_date, 0)
                        media_dates[filename_date] = filename_index + 1
                        filename_ext = pathlib.Path(filename).suffix
                        new_filename = f"{type_classifier}-{filename_date}-WA{filename_index:04}{filename_ext}"
                        media_all.append((new_filename, filename))
                        media_message.append(new_filename)
            whatsapp_buffer.append(
                WhatsappMessageStruct(
                    telegram_id=telegram_id,
                    real_date=real_date,
                    date_str=date_str,
                    time_str=time_str,
                    sender=sender,
                    text=text,
                    media_message=media_message,
                )
            )
        except AttributeError:
            # tbf = str(traceback.format_exc())
            logger.exception(
                "Failed to parse message #%i (ID#%i): found data:%s\n",
                m,
                telegram_id,
                message.prettify(),
                exc_info=True,
            )
        m += 1

    whatsapp_chat = ""
    for message in whatsapp_buffer:
        # Format message in WhatsApp format
        if message.time_str:
            logger.debug("Source data: %s", message)
            whatsapp_message = ""
            if message.text:
                whatsapp_message += f"[{message.date_str}, {message.time_str}] {message.sender}: {message.text}\n"
            if message.media_message:
                for media_item in message.media_message:
                    whatsapp_message += f"[{message.date_str}, {message.time_str}] {message.sender}: {media_item} (file attached)\n"
            logger.debug("Generated message: %s", repr(whatsapp_message))
            whatsapp_chat += whatsapp_message
        else:
            logger.error("Found orphaned parsed message:", message)
    rval = {"chat": whatsapp_chat, "media": media_all}
    return rval


def what_zip(
    transform_input,
    base_path,
    logger: logging.Logger,
    name="Whatsapp Chat - person_name.zip",
):
    """Writes a new ZIP file in the WhatsApp format

    Args:
        transform_input (dict): Source material to amalgamate - from `transform_html_to_whatsapp`
        base_path (Path):       Path to Telegram export base
        name (str):             String name of the resulting ZIP file
    """
    bn = 0
    with zipfile.ZipFile(
        pathlib.Path(base_path.parent, name), "w", compression=zipfile.ZIP_DEFLATED
    ) as zip_object:
        logger.info("Exporting transform block %s", bn)
        chat_agg = ""
        for block in transform_input:
            chat_agg += block["chat"]
            for file in block["media"]:
                logger.info("Adding %s as %s", file[1], file[0])
                try:
                    zip_object.write(
                        filename=pathlib.Path(base_path, file[1]), arcname=file[0]
                    )
                except FileNotFoundError:
                    logger.warning("Could not locate file %s, skipping", file[1])
        zip_object.writestr(zinfo_or_arcname="_chat.txt", data=chat_agg)
    logger.info("ZIP file written to %s", zip_object.filename)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser_filedir = parser.add_mutually_exclusive_group()
    parser_filedir.add_argument("-f", "--file", help="Name of a singular file to parse")
    parser_filedir.add_argument(
        "-d",
        "--dir",
        help="Name of directory of files to parse - will parse every html in this folder",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Enables verbose (debug) logging",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-t",
        "--trace",
        help="Enables additional trace debug logging (implies --verbose)",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()
    global_logger = logging.getLogger("htmltotxt")
    log_han = logging.StreamHandler()
    log_fmt = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s: %(message)s")
    log_han.setFormatter(log_fmt)
    global_logger.addHandler(log_han)
    if args.verbose or args.trace:
        global_logger.setLevel(logging.DEBUG)
    else:
        global_logger.setLevel(logging.INFO)
    if args.trace:
        LOG_TRACE = True
    else:
        LOG_TRACE = False
    if args.file:
        input_file = pathlib.Path(args.file)
        whatsapp_transform = transform_html_to_whatsapp(
            input_file, logger=global_logger
        )
        what_zip(
            [whatsapp_transform], base_path=input_file.parent, logger=global_logger
        )

    else:
        whatsapp_transforms = []
        dir_path = pathlib.Path(args.dir)
        input_index = []
        num_re = re.compile(r"(\D+)?(\d+)?\.html")
        for input_file in dir_path.glob("*.html"):
            file_num = num_re.match(input_file.name).group(2)
            if file_num is None:
                file_num = 0
            else:
                file_num = int(file_num)
            input_index.append((input_file, file_num))
        input_index = sorted(input_index, key=lambda x: x[1])
        global_logger.info("Discovered %i input files", len(input_index))
        for index_entry in input_index:
            input_file = index_entry[0]
            global_logger.info("Processing %s...", input_file)
            whatsapp_transforms.append(
                transform_html_to_whatsapp(input_file, logger=global_logger)
            )

        zip_name = f"Whatsapp Chat - {dir_path.name}.zip"
        what_zip(
            whatsapp_transforms, name=zip_name, base_path=dir_path, logger=global_logger
        )
