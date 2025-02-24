from datetime import datetime
from airflow import DAG
from datetime import timedelta
import requests
from airflow.operators.python import PythonOperator
import pandas as pd
from sqlalchemy import create_engine

default_args = {
    'owner': 'mainguyen',
    'depends_on_past': False,
    'start_date': datetime(2025, 2, 15),
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1)
}


def extract_info():
    headers = {
        'User-Agent': 'Jobsuche/2.9.2 (de.arbeitsagentur.jobboerse; build:1077; iOS 15.1.0) Alamofire/5.4.4',
        'Host': 'rest.arbeitsagentur.de',
        'X-API-Key': 'jobboerse-jobsuche',
        'Connection': 'keep-alive',
    }
    params = {"berufsfeld": "Informatik",
              "page": 1,
              "size": 55}
    arbeitsamt_url = 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/app/jobs'

    response = requests.get(arbeitsamt_url, headers=headers, params=params)
    res = response.json()
    job_lists = res.get('stellenangebote', [])
    return job_lists


def transform_data(**kwargs):
    ti = kwargs['ti']
    job_lists = ti.xcom_pull(task_ids='extract_info')
    job_transformedlists = []
    for job_angebot in job_lists:
        data = {}
        data['beruf'] = job_angebot['beruf']
        data['titel'] = job_angebot['titel']
        data['refnr'] = job_angebot['refnr']
        data['arbeitsort'] = (
            f"{job_angebot['arbeitsort'].get('strasse', 'Unknown')}, "
            f"{job_angebot['arbeitsort'].get('plz', '00000')} "
            f"{job_angebot['arbeitsort'].get('ort', 'Unknown')}, "
            f"{job_angebot['arbeitsort'].get('region', 'Unkown')}"
        )
        data['lat'] = job_angebot['arbeitsort']['koordinaten']['lat']
        data['lon'] = job_angebot['arbeitsort']['koordinaten']['lon']
        data['arbeitgeber'] = job_angebot['arbeitgeber']
        data['veroeffentlichungsdatum'] = job_angebot['aktuelleVeroeffentlichungsdatum']
        data['eintrittsdatum'] = job_angebot['eintrittsdatum']
        job_transformedlists.append(data)
    df = pd.DataFrame(job_transformedlists)
    df.to_csv("./data/job_list.csv", index=False)


engine = create_engine("postgresql+psycopg2://airflow:airflow@postgres/airflow")


def load_data():
    existing_jobs_refnr = pd.read_sql("SELECT refnr FROM job_data",engine)['refnr'].tolist()
    df = pd.read_csv("./data/job_list.csv")
    new_jobs = df[~df['refnr'].isin(existing_jobs_refnr)]
    if not new_jobs.empty:
        new_jobs.to_sql("job_data", engine, if_exists='append', index=False)
        print('Insert new job refnummers')
    else:
        print('No new job update')


with  DAG(
        'jobscraper_dag',
        default_args=default_args,
        description='DAG with ETL process!',
        schedule_interval="0 */6 * * *") as dag:
    extract_task = PythonOperator(task_id='extract_info', python_callable=extract_info)
    transform_task = PythonOperator(task_id='transform_data', python_callable=transform_data)
    load_task = PythonOperator(task_id='load_data',python_callable=load_data)

extract_task >> transform_task >> load_task


