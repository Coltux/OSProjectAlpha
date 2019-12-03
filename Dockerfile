FROM ubuntu:rolling

MAINTAINER cgrant@ou.edu


RUN apt-get update && apt-get install -y locales && rm -rf /var/lib/apt/lists/* \
    && localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

RUN apt-get update && apt-get upgrade -y && apt-get install -y python3-pip ipython3

RUN apt-get install -y vim nmap iputils-ping ssh netcat htop slurm net-tools

ENV GRPC_PYTHON_VERSION 1.15.0

RUN apt-get install -y libprotoc-dev protobuf-compiler

RUN python3 -m pip install --upgrade pip && python3 -m pip install click grpcio grpcio-tools

RUN mkdir -p /usr/src/app
WORKDIR /usr/src/app

# Build python stuff
## On build is only for using this image as a template for another image
#ONBUILD COPY requirements.txt /usr/src/app/
#ONBUILD RUN pip install --no-cache-dir -r requirements.txt
#ONBUILD COPY . /usr/src/app
COPY requirements.txt /usr/src/app/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /usr/src/app

# Create the protobuf files
# RUN protoc --python_out=. rsa.proto # Code below works similarly
RUN python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. GHS.proto

EXPOSE 22
EXPOSE 80
EXPOSE 50050-50100

# Unbuffer to see logs with docker logs <containername>
ENV PYTHONUNBUFFERED=1

# Run the node
CMD ["python3", "node.py"]