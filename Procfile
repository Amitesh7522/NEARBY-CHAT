release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: python manage.py collectstatic --noinput && python manage.py migrate --noinput && daphne -b 0.0.0.0 -p $PORT nearby_chat.asgi:application
