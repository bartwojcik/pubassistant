FROM postgres:9.5
RUN apt-get update && apt-get install -y \
 postgresql-contrib\
 postgresql-plpython3-9.5

