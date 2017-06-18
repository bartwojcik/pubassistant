FROM python:3.5.1
RUN apt-get update && apt-get install -y \
 zlib1g-dev \
 libsasl2-dev \
 tor \
 postgresql-client
RUN groupadd -r user && useradd -r -g user user
RUN chmod 1777 /tmp
ENV PYTHONUNBUFFERED 1
RUN mkdir /code
WORKDIR /code
COPY requirements.txt /code/
RUN pip install --upgrade pip --no-cache-dir &&\
    pip install -r requirements.txt --no-cache-dir

