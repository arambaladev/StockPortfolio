# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Oracle InstantClient
RUN apt update && apt install wget unzip libaio1t64 -y
RUN mkdir -p /opt/oracle
WORKDIR /opt/oracle
RUN wget https://download.oracle.com/otn_software/linux/instantclient/19600/instantclient-basic-linux.x64-19.6.0.0.0dbru.zip
RUN unzip ./ins*.zip
ENV LD_LIBRARY_PATH /opt/oracle/instantclient_19_6:$LD_LIBRARY_PATH
RUN apt remove wget unzip -y && rm /opt/oracle/*zip

WORKDIR /app
# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run the app using gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
