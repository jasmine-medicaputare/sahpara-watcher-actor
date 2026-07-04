FROM apify/actor-python:3.13

COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . ./

RUN echo "Python version:" && python3 --version

CMD ["python3", "-m", "src"]
