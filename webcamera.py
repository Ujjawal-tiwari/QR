from flask import Flask, render_template, request, redirect, url_for, jsonify
import os
import cv2
import pytesseract
from pyzbar import pyzbar
import re
import json
import xml.etree.ElementTree as ET
from PIL import Image

app = Flask(__name__)

# Path to the Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

output_folder = 'static/uploads'
json_output_path = os.path.join(output_folder, "Extracted_data.json")

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

def preprocess_text(text):
    text = re.sub(r'\s+', ' ', text)
    return text

def extract_details_from_image(image_path):
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)
    text = preprocess_text(text)
    aadhaar_pattern = r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
    dob_pattern = r'\b\d{2}[-/]\d{2}[-/]\d{4}\b'
    mobile_pattern = r'\b\d{10}\b'
    name_pattern = r'\b([A-Z][a-z]* [A-Z][a-z]*)\b'
    address_pattern = r'Address:(.*?)(?:\n|$)'
    aadhaar_match = re.search(aadhaar_pattern, text)
    dob_match = re.search(dob_pattern, text)
    mobile_match = re.search(mobile_pattern, text)
    name_matches = re.findall(name_pattern, text)
    name = name_matches[0] if name_matches else None
    address_match = re.search(address_pattern, text, re.DOTALL)
    details = {
        "AadhaarNumber": aadhaar_match.group(0).replace(' ', '').replace('-', '') if aadhaar_match else None,
        "DOB": dob_match.group(0) if dob_match else None,
        "MobileNumber": mobile_match.group(0) if mobile_match else None,
        "Name": name,
        "Address": address_match.group(1).strip().replace('\n', ', ') if address_match else None
    }
    return details

def save_to_xml(details, output_file):
    root = ET.Element("AadhaarDetails")
    for key, value in details.items():
        if value:
            element = ET.SubElement(root, key)
            element.text = value
    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)

def detect_and_save_two_largest_qrs(image, output_folder):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("No contours found.")
        return
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:2]
    qr_data = []
    largest_images = []
    for i, contour in enumerate(contours):
        (x, y, w, h) = cv2.boundingRect(contour)
        qr_code_image = image[y:y + h, x:x + w]
        qr_code_data = decode_qr_code(qr_code_image)
        if qr_code_data:
            json_data = parse_qr_data(qr_code_data)
            if json_data:
                qr_data.append(json_data)
        largest_images.append((w * h, qr_code_image))
    largest_images.sort(key=lambda x: x[0], reverse=True)
    for j, (area, img) in enumerate(largest_images[:2]):
        img_output_path = os.path.join(output_folder, f"image_{j + 1}.png")
        cv2.imwrite(img_output_path, img)
    combined_data = {}
    if qr_data:
        combined_data["QR_data"] = qr_data
    else:
        image_path = os.path.join(output_folder, "captured_image.png")
        cv2.imwrite(image_path, image)
        other_details = extract_details_from_image(image_path)
        if other_details:
            combined_data["adhar_details"] = other_details
        else:
            print("No QR data and no other details found in the image.")
    with open(json_output_path, 'w') as json_file:
        json.dump(combined_data, json_file, indent=4)
        print(f"Extracted data saved to {json_output_path}")

def decode_qr_code(qr_code_image):
    qr_code_data = None
    qr_codes = pyzbar.decode(qr_code_image)
    for qr_code in qr_codes:
        qr_code_data = qr_code.data.decode('utf-8')
        print(f"QR code details: {qr_code_data}")
    return qr_code_data

def parse_qr_data(qr_code_data):
    try:
        root = ET.fromstring(qr_code_data)
        json_data = {root.tag: root.attrib}
        return json_data
    except ET.ParseError:
        print("QR code data is not valid XML.")
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file:
        file_path = os.path.join(output_folder, file.filename)
        file.save(file_path)
        image = cv2.imread(file_path)
        detect_and_save_two_largest_qrs(image, output_folder)
        return redirect(url_for('results'))

@app.route('/results')
def results():
    with open(json_output_path, 'r') as json_file:
        data = json.load(json_file)
    return jsonify(data)

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=3000)   # bhaiya yha par ip and port h,change krne k liye
