FROM node:20-slim

WORKDIR /app

# نصب پکیج سراسری 9router
RUN npm install -g 9router

# تنظیم پیش‌فرض پورت و آی‌پی
ENV HOST=0.0.0.0
ENV PORT=20128

EXPOSE 20128

# اجرای 9router با پشتیبانی از پورت داینامیک رندر
CMD ["sh", "-c", "9router start --host 0.0.0.0 --port ${PORT:-20128}"]
