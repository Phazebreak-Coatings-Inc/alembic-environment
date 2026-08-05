CREATE TABLE users (
  user_id INT PRIMARY KEY,
  username VARCHAR(50) NOT NULL UNIQUE,
  email VARCHAR(100),
  password VARCHAR(100),
  join_date DATE DEFAULT CURRENT_TIMESTAMP
  -- created_by VARCHAR
  -- last_modified_by VARCHAR
);

CREATE TABLE orders (
  order_id INT PRIMARY KEY,
  title VARCHAR(500),
  description VARCHAR(2000),
  user_id INT NOT NULL REFERENCES users (user_id)
  -- created_by VARCHAR
  -- last_modified_by VARCHAR
);
