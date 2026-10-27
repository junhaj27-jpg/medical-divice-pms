FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update
RUN apt-get install -y --no-install-recommends fonts-nanum
ENV PDF_KOREAN_FONT=/usr/share/fonts/truetype/nanum/NanumGothic.ttf
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python manage.py collectstatic --noinput
CMD ["sh","-c","python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
