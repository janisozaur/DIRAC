########################################################################
# $HeadURL$
# File :   BOINCComputingElement.py
# Author : J.Wu
########################################################################

""" BOINC Computing Element 
"""

__RCSID__ = "$Id$"

from DIRAC.Resources.Computing.ComputingElement          import ComputingElement
from DIRAC                                               import S_OK, S_ERROR

import os, bz2, base64,tempfile
from urlparse import urlparse

CE_NAME = 'BOINC'

class BOINCComputingElement( ComputingElement ):

###############################################################################
  def __init__( self, ceUniqueID ):
    """ Standard constructor.
    """

    ComputingElement.__init__( self, ceUniqueID )

    self.ceType = CE_NAME
    self.mandatoryParameters = []
    self.wsdl = None
    self.BOINCClient = None
#define a job prefix based on the wsdl url
    self.suffix = None
# this is for standlone test
#    self.ceParameters['projectURL'] = 'http://mardirac3.in2p3.fr:7788/?wsdl'
#    self.ceParameters['Platform'] = 'Linux_x86_64_glibc-2.5'

###############################################################################
  def createClient( self ):
    """
    This method only can be called after the initialtion of this class. In this 
    method, it will initial some variables and create a soap client for commnication 
    with BOINC server.
    """

    if not self.wsdl:
      self.wsdl = self.ceParameters['projectURL']
    if not self.suffix:
      result = urlparse(self.wsdl)
      self.suffix = result.hostname
    if not self.BOINCClient:
      try:
        from suds.client import Client
        import logging
        logging.basicConfig(format="%(asctime)-15s %(message)s")
        self.BOINCClient = Client(self.wsdl)
      except Exception,x:
        self.log.error( 'Creation of the soap client failed: %s' % str( x ) )
        pass


###############################################################################
  def submitJob( self, executableFile, proxy = None, numberOfJobs = 1 ):
    """ Method to submit job
    """
    self.createClient( )
    # Check if the client is ready
    if not self.BOINCClient:
      return S_ERROR( 'Soap client is not ready' )
    
    self.log.verbose( "Executable file path: %s" % executableFile )

    # if no proxy is supplied, the executable can be submitted directly
    # otherwise a wrapper script is needed to get the proxy to the execution node
    # The wrapper script makes debugging more complicated and thus it is
    # recommended to transfer a proxy inside the executable if possible.
    wrapperContent= ''
    if proxy:
      self.log.verbose( 'Setting up proxy for payload' )

      compressedAndEncodedProxy = base64.encodestring( bz2.compress( proxy.dumpAllToString()['Value'] ) ).replace( '\n', '' )
      compressedAndEncodedExecutable = base64.encodestring( bz2.compress( open( executableFile, "rb" ).read(), 9 ) ).replace( '\n', '' )

      wrapperContent = """#!/bin/bash
/usr/bin/env python << EOF
# Wrapper script for executable and proxy
import os, tempfile, sys, base64, bz2, shutil
try:
  workingDirectory = tempfile.mkdtemp( suffix = '_wrapper', prefix= 'TORQUE_' )
  os.chdir( workingDirectory )
  open( 'proxy', "w" ).write(bz2.decompress( base64.decodestring( "%(compressedAndEncodedProxy)s" ) ) )
  open( '%(executable)s', "w" ).write(bz2.decompress( base64.decodestring( "%(compressedAndEncodedExecutable)s" ) ) )
  os.chmod('proxy',0600)
  os.chmod('%(executable)s',0700)
  os.environ["X509_USER_PROXY"]=os.path.join(workingDirectory, 'proxy')
except Exception, x:
  print >> sys.stderr, x
  sys.exit(-1)
cmd = "./%(executable)s"
print 'Executing: ', cmd
sys.stdout.flush()
os.system( cmd )

shutil.rmtree( workingDirectory )

EOF
""" % { 'compressedAndEncodedProxy': compressedAndEncodedProxy, \
        'compressedAndEncodedExecutable': compressedAndEncodedExecutable, \
        'executable': os.path.basename( executableFile ) }

      fd, name = tempfile.mkstemp( suffix = '_pilotwrapper.py', prefix = 'DIRAC_', dir = os.getcwd() )
      os.close( fd )
      submitFile = name

    else: # no proxy
      submitFile = executableFile
      wrapperContent = self._fromFileToStr( submitFile )

    if not wrapperContent: 
      self.log.error( 'Executable file is empty.' )
      return S_ERROR( 'Executable file is empty.' )

    #Some special symbol can not be transported by xml, 
    #such as less, greater, amp. So, base64 is used here.
    wrapperContent = base64.encodestring( wrapperContent ).replace( "\n",'')

    prefix = os.path.splitext( os.path.basename( submitFile ) )[0].replace( '_pilotwrapper', '' ).replace( 'DIRAC_', '' )
    batchIDList = []
    stampDict = {}
    for i in range( 0, numberOfJobs ):
      jobID = "%s_%d@%s" % ( prefix, i, self.suffix)
      try:
#  print jobID + "\n" + wrapperContent
#  print self.BOINCClient
        result = self.BOINCClient.service.submitJob( jobID, wrapperContent,self.ceParameters['Platform'] )
      except:
        self.log.error( 'Could not submit the pilot %s to the BOINC CE %s, communication failed!' % (jobID, self.wsdl ))
        break;        

      if not result['ok']:
        self.log.warn( 'Didn\'t submit the pilot %s to the BOINC CE %s, the value returned is false!' % (jobID, self.wsdl ))
        break;

      self.log.verbose( 'Submit the pilot %s to the BONIC CE %s' % (jobID, self.wsdl) )
      diracStamp = "%s_%d" % ( prefix, i  )
      batchIDList.append( jobID )
      stampDict[jobID] = diracStamp
    
    if batchIDList:
      resultRe = S_OK( batchIDList )
      resultRe['PilotStampDict'] = stampDict
    else:
      resultRe = S_ERROR('Submit no pilot to BOINC CE %s' % self.wsdl)  
    return resultRe

#############################################################################
  def getCEStatus( self ):
    """ Method to get the BONIC CE dynamic jobs information.
    """
    self.createClient( )
    # Check if the client is ready
    if not self.BOINCClient:
      self.log.error( 'Soap client is not ready.' )
      return S_ERROR( 'Soap client is not ready.' )
    
    try:
      result = self.BOINCClient.service.getDynamicInfo( )
    except:
      self.log.error( 'Could not get the BOINC CE %s dynamic jobs information, communication failed!' % self.wsdl )
      return S_ERROR( 'Could not get the BOINC CE %s dynamic jobs information, communication failed!' % self.wsdl )

    if not result['ok']:
      self.log.warn( 'Did not get the BONIC CE %s dynamic jobs information, the value returned is false!' % self.wsdl  )
      return S_ERROR( 'Did not get the BONIC CE %s dynamic jobs information, the value returned is false!' % self.wsdl )
      
     
    self.log.verbose( 'Get the BOINC CE %s dynamic jobs info.' % self.wsdl )

    resultRe = S_OK()
    resultRe['WaitingJobs'] = result['values'][0][0]
    resultRe['RunningJobs'] = result['values'][0][1]
    resultRe['SubmittedJobs'] = 0
    self.log.verbose( 'Waiting Jobs: ', resultRe['WaitingJobs'] )
    self.log.verbose( 'Running Jobs: ', resultRe['RunningJobs'] )
    return resultRe

#############################################################################
  def getJobStatus( self, jobIDList ):
    """ Get the status information about jobs in the given list
    """
    self.createClient( )
    # Check if the client is ready
    if not self.BOINCClient:
      self.log.error( 'Soap client is not ready.' )
      return S_ERROR( 'Soap client is not ready.' )
    
    wsdl_jobIDList = self.BOINCClient.factory.create( 'stringArray' )
    for job in jobIDList :
      try:
        job = job.split("@")[0]
      except:
        self.log.debug("The job id is %s" % job)
        pass
      wsdl_jobIDList[0].append( job )
    
    try:  
      result = self.BOINCClient.service.getJobStatus( wsdl_jobIDList )
    except:
      self.log.error( 'Could not get the status about jobs in the list from the BONIC CE %s, commnication failed!' % self.wsdl )
      return S_ERROR( 'Could not get the status about jobs in the list from the BONIC CE %s, commnication failed!' % self.wsdl )

    if not result['ok']:
      self.log.warn( 'Did not get the status about jobs in the list from the BONIC CE %s, the value returned is false!' % self.wsdl )
      return S_ERROR( 'Did not get the status about jobs in the list from the BONIC CE %s, the value returned is false!' % self.wsdl )
    self.log.debug( 'Got the status about jobs in list from the BOINC CE %s.' % self.wsdl )
    resultRe = { }
    for jobStatus in result['values'][0]:
      (jobID, status) = jobStatus.split(":")
      jobID = "%s@%s" % ( jobID, self.suffix)
      resultRe[jobID] = status

    return S_OK( resultRe )

#############################################################################
  def getJobOutput( self, jobID, localDir = None ):
    """ Get the stdout and stderr outputs of the specified job . If the localDir is provided,
        the outputs are stored as files in this directory and the name of the files are returned.
        Otherwise, the outputs are returned as strings. 
    """
    self.createClient( )
    # Check if the client is ready
    if not self.BOINCClient:
      self.log.error( 'Soap client is not ready.' )
      return S_ERROR( 'Soap client is not ready.' )

    try: 
      tempID = jobID.split("@")[0]
    except:
      tempID = jobID

    try:
      result = self.BOINCClient.service.getJobOutput( tempID )
    except:
      self.log.error( 'Could not get the outputs of job %s from the BONIC CE %s, commnication failed!' % (jobID, self.wsdl) )
      return S_ERROR( 'Could not get the outputs of job %s from the BONIC CE %s, commnication failed!' % (jobID, self.wsdl) )
    if not result['ok']:
      self.log.warn( 'Did not get the outputs of job %s from the BONIC CE %s, the value returned is false!' % (jobID, self.wsdl) )
      return S_ERROR( 'Did not get the outputs of job %s from the BONIC CE %s, the value returend is false!' % (jobID, self.wsdl) )

    self.log.debug( 'Got the outputs of job %s from the BONIC CE %s.' % (jobID, self.wsdl) )

    strOutfile = base64.decodestring( result['values'][0][0] )
    strErrorfile = base64.decodestring( result['values'][0][1] )
    if localDir:
      outFile = os.path.join( localDir, 'BOINC_%s.out' % jobID )
      self._fromStrToFile( strOutfile, outFile )

      errorFile = os.path.join( localDir, 'BOINC_%s.err' % jobID )
      self._fromStrToFile( strErrorfile, errorFile )

      return S_OK( ( outFile, errorFile ) )
    else:
      # Return the outputs as a string
      return S_OK( ( strOutfile, strErrorfile ) )

##############################################################################
  def _fromFileToStr(self, fileName ):
    """ Read a file and return the file content as a string
    """
    strFile = ''
    if( os.path.exists( fileName )):
      try:
        fileHander = open ( fileName, "r" )
        strFile = fileHander.read ( ) 
      except:
        self.log.verbose( "To read file %s failed!\n" % fileName)
        pass
      finally:
        if fileHander:
          fileHander.close( )
    return strFile
 
#####################################################################
  def _fromStrToFile(self, strContent, fileName ):
    """ Write a string to a file
    """
    try:
      fileHandler = open ( fileName, "w" )
      fileHandler.write ( strContent ) 
    except:
      self.log.verbose( "To create %s failed!" % fileName )
      pass
    finally:
      if fileHandler:
        fileHandler.close( )

# testing this
if __name__ == "__main__":

  test_boinc = BOINCComputingElement( 12 )
  test_submit = 1
  test_getStatus = 2
  test_getDynamic = 4
  test_getOutput = 8
  test_parameter = 4    
  jobID ='zShvbK_0@mardirac3.in2p3.fr'
  if test_parameter & test_submit: 
    fd, fname = tempfile.mkstemp( suffix = '_pilotwrapper.py', prefix = 'DIRAC_', dir = "/home/client/dirac/data/" )
    os.close( fd )
    fd = open ( fname,"w" )
    fd.write('#!/usr/bin/env sh\necho \"I am stadard out\" &gt;&amp;1 \necho \"I am stadard error\" &gt;&amp;2 ')
    fd.close()
    result = test_boinc.submitJob( fname )
 
    if not result['OK']:
      print result['Message']
    else:
      jobID = result['Value'][0]
      print "Successfully submit a job %s" % jobID

  if test_parameter & test_getStatus:
    jobTestList = ["Uu0ghO_0@mardirac3.in2p3.fr", "1aDmIf_0@mardirac3.in2p3.fr",jobID] 
    jobStatus = test_boinc.getJobStatus( jobTestList )
    if not jobStatus['OK']:
      print jobStatus['Message']
    else:
      for id_ in jobTestList:
        print 'The status of the job %s is %s' % (id_, jobStatus['Value'][id_])

  if test_parameter & test_getDynamic:
    serverState = test_boinc.getCEStatus()

    if not serverState['OK']:
      print serverState['Message']
    else:
      print 'The number of jobs waiting is %s' % serverState['WaitingJobs']
      print 'The number of jobs running is %s' % serverState['RunningJobs']
  
  if test_parameter & test_getOutput:
    outstate = test_boinc.getJobOutput( jobID, "/tmp/" )

    if not outstate['OK']:
      print outstate['Message']
    else:
      print "Please check the directory /tmp for the output and error files of job %s" %jobID 


#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#EOF#
