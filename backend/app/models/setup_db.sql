-- Create the user
CREATE USER time_game WITH PASSWORD '3VIspJYH2vfWkFLHb2BnJw';

-- Create the database
CREATE DATABASE timelogger;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE timelogger TO time_game;
