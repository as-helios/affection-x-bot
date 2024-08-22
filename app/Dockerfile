FROM python:3.12
RUN apt update
RUN apt upgrade -y
RUN apt install -y build-essential
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["sh", "-c", "python main.py"]
