FROM node:20-slim

WORKDIR /app

# نصب 9router
RUN npm install -g 9router

ENV HOST=0.0.0.0
ENV PORT=10000
ENV CI=true

EXPOSE 10000

# اجرای 9router و زنده نگه‌داشتن پروسس اصلی در رندر
CMD ["sh", "-c", "9router start --host 0.0.0.0 --port ${PORT:-10000} && tail -f /dev/null"]
