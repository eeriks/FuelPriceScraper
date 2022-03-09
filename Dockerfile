FROM python:3.10-alpine
RUN pip install requests
COPY main.py /app/main.py

CMD ["python", "-OO", "/app/main.py"]