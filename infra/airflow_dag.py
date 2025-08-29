"""
Example Airflow DAG for Web Agent orchestration
Phase 2 implementation for production scheduling
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.email import EmailOperator
from airflow.models import Variable
import asyncio
import sys
import os

# Add the agent modules to Python path
sys.path.append('/opt/airflow/dags/web-agent')

# Default arguments for the DAG
default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': datetime(2025, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=15),
    'email': ['admin@yourcompany.com']
}

# Create the DAG
dag = DAG(
    'web_agent_scraping',
    default_args=default_args,
    description='Web scraping and file retrieval agent',
    schedule_interval=timedelta(hours=24),  # Run daily
    catchup=False,
    max_active_runs=1,  # Prevent overlapping runs
    tags=['web-scraping', 'data-collection']
)


def run_web_agent(**context):
    """
    Python function to run the web agent
    """
    from modules.orchestrator import AgentOrchestrator
    
    async def async_run():
        orchestrator = AgentOrchestrator('/opt/airflow/dags/web-agent/config')
        await orchestrator.initialize()
        
        # Get specific sites from Airflow Variables if configured
        site_names = Variable.get('web_agent_sites', default_var=None)
        if site_names:
            site_names = site_names.split(',')
        
        result = await orchestrator.run_single_cycle(site_names)
        
        # Log results to Airflow context
        context['task_instance'].xcom_push(key='scraping_results', value=result)
        
        return result
    
    # Run the async function
    result = asyncio.run(async_run())
    
    # Check if we should fail the task based on results
    if result.get('processed_sites', 0) == 0:
        raise Exception("No sites were processed successfully")
    
    return result


def check_results(**context):
    """
    Check scraping results and determine if we should alert
    """
    results = context['task_instance'].xcom_pull(key='scraping_results')
    
    total_sites = results.get('processed_sites', 0)
    total_downloads = results.get('total_downloads_successful', 0)
    
    # Define success criteria
    min_expected_sites = int(Variable.get('min_expected_sites', default_var='1'))
    min_expected_downloads = int(Variable.get('min_expected_downloads', default_var='1'))
    
    success = (
        total_sites >= min_expected_sites and 
        total_downloads >= min_expected_downloads
    )
    
    if not success:
        raise Exception(
            f"Scraping results below threshold: "
            f"{total_sites} sites, {total_downloads} downloads"
        )
    
    return {
        'success': success,
        'sites_processed': total_sites,
        'files_downloaded': total_downloads
    }


def cleanup_old_data(**context):
    """
    Cleanup old data and temporary files
    """
    from modules.orchestrator import AgentOrchestrator
    
    async def async_cleanup():
        orchestrator = AgentOrchestrator('/opt/airflow/dags/web-agent/config')
        await orchestrator.initialize()
        await orchestrator.cleanup()
    
    asyncio.run(async_cleanup())
    return "Cleanup completed"


# Task 1: Health check
health_check = BashOperator(
    task_id='health_check',
    bash_command='python /opt/airflow/dags/web-agent/modules/orchestrator.py --status',
    dag=dag
)

# Task 2: Run web agent
run_agent = PythonOperator(
    task_id='run_web_agent',
    python_callable=run_web_agent,
    dag=dag
)

# Task 3: Check results
validate_results = PythonOperator(
    task_id='validate_results',
    python_callable=check_results,
    dag=dag
)

# Task 4: Cleanup (runs weekly)
cleanup = PythonOperator(
    task_id='cleanup_old_data',
    python_callable=cleanup_old_data,
    dag=dag,
    # Only run on Sundays
    schedule_interval='0 2 * * 0'  # 2 AM on Sundays
)

# Task 5: Success notification
success_email = EmailOperator(
    task_id='send_success_email',
    to=['admin@yourcompany.com'],
    subject='Web Agent Scraping Completed Successfully',
    html_content="""
    <h3>Web Agent Scraping Results</h3>
    <p>The daily web scraping job completed successfully.</p>
    <p><strong>Results:</strong></p>
    <ul>
        <li>Sites processed: {{ task_instance.xcom_pull(task_ids='validate_results')['sites_processed'] }}</li>
        <li>Files downloaded: {{ task_instance.xcom_pull(task_ids='validate_results')['files_downloaded'] }}</li>
    </ul>
    <p>Check the logs for detailed information.</p>
    """,
    dag=dag,
    trigger_rule='all_success'
)

# Task 6: Failure notification
failure_email = EmailOperator(
    task_id='send_failure_email',
    to=['admin@yourcompany.com'],
    subject='Web Agent Scraping Failed',
    html_content="""
    <h3>Web Agent Scraping Failed</h3>
    <p>The daily web scraping job failed. Please check the logs for details.</p>
    <p>Common issues:</p>
    <ul>
        <li>Network connectivity problems</li>
        <li>Website structure changes</li>
        <li>Rate limiting or blocking</li>
        <li>Configuration errors</li>
    </ul>
    <p>Review the Airflow logs and agent logs for more information.</p>
    """,
    dag=dag,
    trigger_rule='one_failed'
)

# Define task dependencies
health_check >> run_agent >> validate_results >> [success_email, failure_email]

# Weekly cleanup runs independently
cleanup

# Optional: Add a sensor to wait for external trigger
# from airflow.sensors.filesystem import FileSensor
# 
# wait_for_trigger = FileSensor(
#     task_id='wait_for_trigger_file',
#     filepath='/opt/airflow/triggers/run_web_agent.trigger',
#     fs_conn_id='fs_default',
#     poke_interval=300,  # Check every 5 minutes
#     dag=dag
# )
# 
# wait_for_trigger >> health_check


# Add documentation
dag.doc_md = """
## Web Agent Scraping DAG

This DAG orchestrates the web scraping agent to collect files from configured websites.

### Tasks:
1. **health_check**: Verify agent is properly configured
2. **run_web_agent**: Execute the main scraping process
3. **validate_results**: Check if results meet minimum expectations
4. **send_success_email**: Notify on successful completion
5. **send_failure_email**: Alert on failures
6. **cleanup_old_data**: Weekly cleanup of old data (runs independently)

### Configuration:
- Set `web_agent_sites` Variable to specify which sites to scrape (comma-separated)
- Set `min_expected_sites` Variable for minimum site count threshold
- Set `min_expected_downloads` Variable for minimum download count threshold

### Monitoring:
- Check Airflow logs for execution details
- Agent logs are stored in `/opt/airflow/dags/web-agent/data/logs/`
- Email notifications are sent on success/failure

### Troubleshooting:
- Verify configuration files are present and valid
- Check network connectivity from Airflow workers
- Review site-specific error logs
- Ensure proper permissions on data directories
"""
