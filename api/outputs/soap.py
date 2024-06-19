import requests


def send_soap_request(url, body, headers):
    """
    Send SOAP request

    Params:
        * url <string>
        * headers <json>
        * body <string>

    Response:
        * status_code
        * content: decoded by 'utf-8'

    Sample params and response:
        url="https://www.dataaccess.com/webservicesserver/NumberConversion.wso"
        headers = {'content-type': 'text/xml'}
        body = '<?xml version="1.0" encoding="utf-8"?> \
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"> \
          <soap:Body> \
            <NumberToWords xmlns="http://www.dataaccess.com/webservicesserver/"> \
              <ubiNum>125</ubiNum> \
            </NumberToWords> \
          </soap:Body> \
        </soap:Envelope>'

        status_code: 200
        content: b'<?xml version="1.0" encoding="utf-8"?>\r\n<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">\r\n  <soap:Body>\r\n    <m:NumberToWordsResponse xmlns:m="http://www.dataaccess.com/webservicesserver/">\r\n      <m:NumberToWordsResult>one hundred and twenty five </m:NumberToWordsResult>\r\n    </m:NumberToWordsResponse>\r\n  </soap:Body>\r\n</soap:Envelope>'
    """
    response = requests.post(url, data=body, headers=headers)
    status_code = response.content
    content = response.content

    if response.status_code == 200:
        content = content.decode("utf-8")

    return response
