FROM python:3.12-slim

# snmp tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends snmp && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Enable standard MIBs (Printer MIB, HOST-RESOURCES, etc.)
RUN echo "mibs :" > /etc/snmp/snmp.conf

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 2026

CMD ["python", "main.py"]
