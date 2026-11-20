set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

cd main

python manage.py collectstatic --no-input

python manage.py migrate --no-input
