import logging
import random
import time
from zplgrf import GRF
from base64 import b64decode, b64encode
import img2pdf
from PIL import Image
import os
import requests

try:
    from PyPDF2 import PdfFileReader, PdfFileWriter
except ImportError:
    from pyPdf import PdfFileReader, PdfFileWriter

from api.operations.email_senders import send_email_to_developers
from api.common import trace_error

logger = logging.getLogger(__name__)


def base64_to_pdf(base64, pdf_path):
    try:
        bytes = b64decode(base64, validate=True)

        if bytes[0:4] != b"%PDF":
            raise ValueError("Missing the PDF file signature")

        f = open(pdf_path, "wb")
        f.write(bytes)
        f.close()
        return True
    except Exception as e:
        error_msg = f"@300 Error on base64_to_pdf(): {str(e)}"
        logger.info(error_msg)
        send_email_to_developers("PDF covertion error", error_msg)
        return False


def pdf_to_base64(pdf_path):
    try:
        f = open(pdf_path, "rb")
        return b64encode(f.read())
    except Exception as e:
        error_msg = f"@301 Error on pdf_to_base64(): {str(e)}"
        logger.info(error_msg)
        send_email_to_developers("PDF covertion error", error_msg)
        return False


def pdf_to_zpl(pdf_path, zpl_path):
    try:
        with open(pdf_path, "rb") as pdf:
            pages = GRF.from_pdf(pdf.read(), "DEMO")
            f = open(zpl_path, "w")

            for grf in pages:
                f.write(grf.to_zpl(compression=2, print_mode="T"))

            f.close()
            return True
    except Exception as e:
        trace_error.print()
        error_msg = f"@301 Error on pdf_to_zpl(): {str(e)}"
        logger.info(error_msg)
        send_email_to_developers("PDF covertion error", error_msg)
        return False


def pdf_merge(input_files, output_file_url):
    LOG_ID = "[PDF MERGE]"
    logger.info(
        f"{LOG_ID} Started!\nInput files: {input_files}\nOutput file: {output_file_url}"
    )

    try:
        # First open all the files, then produce the output file, and
        # finally close the input files. This is necessary because
        # the data isn't read from the input files until the write
        # operation. Thanks to
        # https://stackoverflow.com/questions/6773631/problem-with-closing-python-pypdf-writing-getting-a-valueerror-i-o-operation/6773733#6773733
        input_streams = []
        output_stream = open(output_file_url, "w+b")
        writer = PdfFileWriter()

        for input_file in input_files:
            input_streams.append(open(input_file, "rb"))

        for reader in map(PdfFileReader, input_streams):
            for n in range(reader.getNumPages()):
                writer.addPage(reader.getPage(n))

        writer.write(output_stream)
    except Exception as e:
        trace_error.print()
        error_msg = f"{LOG_ID} Error: {str(e)}"
        logger.error(error_msg)
    finally:
        for f in input_streams:
            f.close()

        output_stream.close()
        logger.info(f"{LOG_ID} Finished!")


def rotate_pdf(input_path):
    try:
        pdf_in = open(input_path, "rb")
        pdf_reader = PdfFileReader(pdf_in)
        pdf_writer = PdfFileWriter()

        for pagenum in range(pdf_reader.numPages):
            page = pdf_reader.getPage(pagenum)
            page.rotateClockwise(90)
            pdf_writer.addPage(page)

        output_path = input_path[:-4] + "_rotated.pdf"
        pdf_out = open(output_path, "wb")
        pdf_writer.write(pdf_out)
        pdf_out.close()
        pdf_in.close()
        return output_path
    except Exception as e:
        trace_error.print()
        error_msg = f"@301 Error on rotate_pdf(): {str(e)}"
        logger.info(error_msg)
        send_email_to_developers("PDF rotation error", error_msg)
        return False
    
def rotate_and_shrink_pdf(input_path, shrink_ratio=0.85):
    try:
        pdf_in = open(input_path, "rb")
        pdf_reader = PdfFileReader(pdf_in)
        pdf_writer = PdfFileWriter()

        for pagenum in range(pdf_reader.numPages):
            page = pdf_reader.getPage(pagenum)
            page.scaleBy(shrink_ratio) 
            page.rotateClockwise(90)
            pdf_writer.addPage(page)

        output_path = input_path[:-4] + "_rotated.pdf"
        pdf_out = open(output_path, "wb")
        pdf_writer.write(pdf_out)
        pdf_out.close()
        pdf_in.close()
        return output_path
    except Exception as e:
        trace_error.print()
        error_msg = f"@301 Error on rotate_pdf(): {str(e)}"
        logger.info(error_msg)
        send_email_to_developers("PDF rotation error", error_msg)
        return False


def zpl_to_png(
    zpl_path, png_path
):  # png_path does not include filename since several png files can be generated
    try:
        if not os.path.exists(png_path):
            # Create the directory
            os.makedirs(png_path)
        with open(zpl_path, "r") as zpl:
            zpl_code = zpl.read()
            grfs = GRF.from_zpl(zpl_code)

            if grfs:
                for i, grf in enumerate(grfs):
                    img_path = f"{png_path}/output-png{i}.png"
                    grf.to_image().save(img_path, "PNG")
            else:
                # adjust print density (8dpmm), label width (4 inches), label height (6 inches), and label index (0) as necessary
                url = "http://api.labelary.com/v1/printers/8dpmm/labels/4x6/0/"
                files = {"file": zpl_code}
                response = requests.post(url, files=files, stream=True)

                if response.status_code == 200:
                    with open(f"{png_path}/output-png.png", "wb") as f:
                        f.write(response.content)
                    # Delay for 0.2 seconds between each request
                    time.sleep(0.2)
            return True
    except Exception as e:
        trace_error.print()
        error_msg = f"@301 Error on zpl_to_png(): {str(e)}"
        send_email_to_developers("ZPL to PNG covertion error", error_msg)
    return False


def png_to_pdf(png_path, pdf_path):
    # png_path does not include filename since several png files merged into one pdf file
    try:
        # opening or creating pdf file
        file = open(pdf_path, "wb")

        # Iterate over files in the directory
        for filename in os.listdir(png_path):
            img_path = os.path.join(png_path, filename)
            if os.path.isfile(img_path):
                # opening image
                image = Image.open(img_path)

                # converting into chunks using img2pdf
                pdf_bytes = img2pdf.convert(image.filename)

                # writing pdf files with chunks
                file.write(pdf_bytes)

                # closing image file
                image.close()
        file.close()
    except Exception as e:
        trace_error.print()
        error_msg = f"@301 Error on png_to_pdf(): {str(e)}"
        logger.info(error_msg)


def zpl_to_pdf(zpl_path, pdf_path):
    try:
        png_path = (
            f"{os.getcwd()}/temp_pngfiles_{str(random.randrange(0, 100000)).zfill(6)}"
        )
        if zpl_to_png(zpl_path, png_path):
            if png_to_pdf(png_path, pdf_path):
                for filename in os.listdir(png_path):
                    img_path = os.path.join(png_path, filename)
                    if os.path.isfile(img_path):
                        os.remove(img_path)
                os.rmdir(png_path)
                return True
    except Exception as e:
        trace_error.print()
        error_msg = f"@301 Error on zpl_to_pdf(): {str(e)}"
        logger.info(error_msg)
        send_email_to_developers("ZPL to PDF covertion error", error_msg)
