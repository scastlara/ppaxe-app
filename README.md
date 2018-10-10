# ppaxe-app
Web application for retrieving protein-protein interactions using ppaxe.

### Screenshot

<img src="https://raw.githubusercontent.com/scastlara/ppaxe-app/master/static/example-screenshot.png"  width=800/>


### Creating sqlite database

```py
import sqlite3

db = sqlite3.connect('mydb')
cursor = db.cursor();

cursor.execute("""
CREATE TABLE jobs (
  id integer PRIMARY KEY, 
  date timestamp,
  updated timestamp,
  progress integer,
  percentage numeric
);
cursor.commit();

""")
```
