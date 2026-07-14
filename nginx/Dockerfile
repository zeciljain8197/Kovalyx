# Adds openssl (absent from the base image) so
# generate_dev_cert_and_start.sh can create a self-signed placeholder
# certificate when no real one is mounted yet.
FROM nginx:1.27-alpine

RUN apk add --no-cache openssl
