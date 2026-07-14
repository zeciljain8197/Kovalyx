# Referenced by docker-compose.yml's streamlit-monitor service
# (context: ./streamlit_monitor, dockerfile: Dockerfile) but never
# written in the session that built streamlit_monitor/'s Python files.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
