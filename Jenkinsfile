pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                echo "Checking out branch: ${env.BRANCH_NAME}"
                checkout scm
            }
        }

        stage('Build') {
            steps {
                echo "Building the project on branch: ${env.BRANCH_NAME}"
            }
        }

        stage('Test') {
            steps {
                echo "Running tests for ${env.BRANCH_NAME}"
            }
        }

        stage('Deploy Simulation') {
            steps {
                echo "Simulating deployment for ${env.BRANCH_NAME}"
            }
        }
    }

    post {
        success {
            echo "✅ Build completed successfully for branch: ${env.BRANCH_NAME}"
        }
        failure {
            echo "❌ Build failed for branch: ${env.BRANCH_NAME}"
        }
    }
}
