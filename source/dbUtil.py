#===============================================================================
#    Magstripe Attendance Database System
#===============================================================================
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>. 
#===============================================================================

import os
import re
import sys
from datetime import datetime

import constants as c
import psycopg2

# The MySQLdb module must be available
try:
    import psycopg2
except ImportError:
    print ("This program requires the psycopg2 module to be installed. "
            "\nOn Ubuntu-based distros the package is \"python-psycopg2\". Exiting.")
    sys.exit(1) 


class DB:
    def __init__(self, dbHost, dbDatabase, dbUsersTable, dbVisitsTable, dbUser, dbPass):
        self.dbConn = None
        self.dbHost = dbHost
        self.dbDatabase = dbDatabase
        self.dbUsersTable = dbUsersTable
        self.dbVisitsTable = dbVisitsTable
        self.dbUser = dbUser
        self.dbPass = dbPass

    def connect(self):
    #===========================================================================
    # Connect to db with given info - need to fix error system
    #===========================================================================    
        # If a password was not given, ask for it
        if self.dbPass == "":
            self.dbPass = getDbPass()

        try:# Connect to the database server
            self.dbConn = psycopg2.connect(database = self.dbDatabase, user = self.dbUser, password = self.dbPass, host = self.dbHost)
            return c.SUCCESS         
        except psycopg2.Error as e:
            #if "user denied" in e.args[1]:  # Bad password error
            print("\n",e)
            #if "password authentication" in e:
            #   return c.BAD_PASSWD
            #else:  # Other error
                #return c.FAILURE


    def close(self):
    #===========================================================================
    # Close out db connection
    #===========================================================================
        if self.dbConn is not None:
            self.dbConn.close()

    def addCard(self, CUID, userID):
    #===========================================================================
    # add a CUID and userID to the database
    #===========================================================================
        # Init some stuff that could cause problems if not initialized
        sqlError = None
        # Get a cursor to the DB
        cursor = self.dbConn.cursor()
      
        try:
            # Add the new record into the DB
            cursor.execute("""INSERT INTO %s (CUID, name) values (\'%s\', \'%s');""" % (self.dbUsersTable, CUID, userID))
            status = c.SUCCESS
        
        except psycopg2.Error as e:
            status = c.SQL_ERROR
            sqlError = e
        
        finally:
            cursor.close()

        return {"addCardStatus": status, "userID": userID, "CUID": CUID, "sqlError": sqlError}

    def checkIn(self, CUID):
    #===========================================================================
    # Check in to db with CUID already in db
    #===========================================================================
        # Init some stuff that could cause problems if not initialized
        status = c.FAILURE
        userID = None
        sqlError = None

        # Get a cursor to the DB
        if self.dbConn is not None:
            cursor = self.dbConn.cursor()
        else:
            print("dbConn is None")

        try:
            cursor.execute("""BEGIN TRANSACTION;""")
            # Get the last check-in time
            cursor.execute("""SELECT last_checkIn FROM %s WHERE CUID=\'%s\';""" % (self.dbUsersTable, CUID))

            # Ensure that the card is in the database
            if cursor.rowcount == 0:
                status = c.CUID_NOT_IN_DB
                # Raise a generic exception to break out of the try block
                raise Exception
            else:
                result = cursor.fetchone()

                # Verify the check-in times
            if c.ALLOW_CHECKIN_WITHIN_HOUR:
                status = c.SUCCESS
            else:
                status = self.checkCheckInTime(result[0])


            if status == c.SUCCESS:
                # Update the database with the new visits         
                cursor.execute("""UPDATE %s SET last_checkIN=\'%s\' WHERE CUID=\'%s\';""" % (self.dbUsersTable, datetime.now(), CUID))
                #cursor.execute("""UPDATE %s SET last_checkIn=\'%s\';""" % (self.dbUsersTable, datetime.))
                # Grab the user ID that just checked-in to print confirmation
                cursor.execute("""SELECT name FROM %s WHERE CUID=\'%s\';""" % (self.dbUsersTable, CUID))

                userID = cursor.fetchone()[0]
        except psycopg2.Error as e:
            status = c.SQL_ERROR
            sqlError = e
        except Exception as e:
            print(e)
            pass
        finally:
            cursor.execute("""END TRANSACTION;""")
            cursor.close()
        
        return {"checkInStatus": status, "userID": userID, "CUID": CUID, "sqlError": sqlError}

   
    def checkCheckInTime(self, lastCheckIn):
    #===========================================================================
    # Verifies that we are not checking into the past or the future
    #===========================================================================
        # Get the current date/time
        curDate = datetime.now()

        # The last_checkIn column was added after the DB was initially populated meaning it could be a NoneType
        # Only check the dates if this is not the case
        if lastCheckIn and datetime.date(curDate) == datetime.date(lastCheckIn):
            tmzAdjust = 0
         
            # Check that the current system time is at least one hour greater than the last check-in time
            if (datetime.time(curDate).hour+tmzAdjust == datetime.time(lastCheckIn).hour or
                (datetime.time(curDate).hour+tmzAdjust == datetime.time(lastCheckIn).hour+1 and
                datetime.time(curDate).minute < datetime.time(lastCheckIn).minute)):
                return c.BAD_CHECKIN_TIME
            # If the current system time is before the check-in time, do not allow check-in
            elif datetime.time(curDate).hour+tmzAdjust < datetime.time(lastCheckIn).hour:
                return c.FUTURE_CHECKIN_TIME
        # If the current system date is before the check-in date, do not allow check-in
        elif lastCheckIn and datetime.date(curDate) < datetime.date(lastCheckIn):
            return c.FUTURE_CHECKIN_TIME
        else:
            return c.SUCCESS


    def showVisits(self, userID=""):
    #===========================================================================
    # Check visits associated with userID and return value
    #===========================================================================
        # Init result and sqlError
        result = None
        sqlError = None

        # Get a cursor to the DB
        cursor = self.dbConn.cursor()

        try:
            # Either get all user ID's and visits from DB or just one user ID
            if userID == "":
                cursor.execute("""SELECT userID, visits FROM %s ORDER BY visits DESC;""" % (self.dbUsersTable))
            else:
                cursor.execute("""SELECT userID, visits FROM %s WHERE userID=\'%s\';""" % (self.dbUsersTable, userID))

            # Show error if no results (user ID is not in database)
            if cursor.rowcount == 0:
                status = c.NO_RESULTS
            else:
                result = cursor.fetchall()
                status = c.SUCCESS

        except psycopg2.Error as e:
            status = c.SQL_ERROR
            sqlError = e
        finally:
            cursor.close()
            return {"showVisitsStatus": status, "visitsTuple": result, "sqlError": sqlError}
