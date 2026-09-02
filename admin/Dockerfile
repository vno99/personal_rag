FROM python:3.12-slim

WORKDIR /home/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nano curl unzip git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.6.0+cpu --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY admin/requirements.txt admin/requirements.txt
RUN pip install --no-cache-dir -r admin/requirements.txt

COPY . .

CMD streamlit run --server.port $PORT admin/app.py
