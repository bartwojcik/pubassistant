FROM nginx:1.9
COPY pubassistant.nginxconf /etc/nginx/conf.d/pubassistant.conf
COPY cert.key.pem /etc/ssl/cert.key.pem
COPY cert.pem /etc/ssl/cert.pem
RUN rm /etc/nginx/conf.d/default.conf
