ARG BUILD_FROM
FROM $BUILD_FROM

# Home Assistant OS does not ship libusb, needed by pyusb to talk to the
# uDMX-compatible USB adapter.
RUN apk add --no-cache libusb libusb-dev bash

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

COPY app /app
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
