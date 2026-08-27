web: daphne -b 0.0.0.0 -p $PORT nearby_chat.asgi:application
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
