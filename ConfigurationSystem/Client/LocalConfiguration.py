# $HeadURL$
__RCSID__ = "$Id$"

import sys
import os
import getopt
import types

import DIRAC
from DIRAC import gLogger
from DIRAC import S_OK, S_ERROR

from DIRAC.ConfigurationSystem.Client.ConfigurationData import gConfigurationData
from DIRAC.ConfigurationSystem.private.Refresher import gRefresher
from DIRAC.ConfigurationSystem.Client.PathFinder import getServiceSection, getAgentSection

class LocalConfiguration:

  def __init__( self, defaultSectionPath = "" ):
    self.currentSectionPath = defaultSectionPath
    self.mandatoryEntryList = []
    self.optionalEntryList = []
    self.commandOptionList = []
    self.unprocessedSwitches = []
    self.additionalCFGFiles = []
    self.parsedOptionList = []
    self.cliAdditionalCFGFiles = []
    self.__registerBasicOptions()
    self.isParsed = False
    self.componentName = "Unknown"
    self.componentType = False
    self.loggingSection = "/DIRAC"
    self.initialized = False
    self.csDisabled = False
    self.csDisabledServers = ""

  def disableParsingCommandLine( self ):
      self.isParsed = True

  def __getAbsolutePath( self, optionPath ):
    if optionPath[0] == "/":
      return optionPath
    else:
      return "%s/%s" % ( self.currentSectionPath, optionPath )

  def addMandatoryEntry( self, optionPath ):
    self.mandatoryEntryList.append( optionPath )

  def addDefaultEntry( self, optionPath, value ):
    if optionPath[0] == "/":
      if not gConfigurationData.extractOptionFromCFG( optionPath ):
        self.__setOptionValue( optionPath, value )
    else:
      self.optionalEntryList.append( ( optionPath,
                                     str( value ) ) )
  def addCFGFile( self, filePath ):
    self.additionalCFGFiles.append( filePath )

  def __setOptionValue( self, optionPath, value ):
    gConfigurationData.setOptionInCFG( self.__getAbsolutePath( optionPath ),
                                       str( value ) )

  def __registerBasicOptions( self ):
    self.registerCmdOpt( "o:", "option=", "Option=value to add",
                         self.__setOptionByCmd )
    self.registerCmdOpt( "s:", "section=", "Set base section for relative parsed options",
                         self.__setSectionByCmd )
    self.registerCmdOpt( "c:", "cert=", "Use server certificate to connect to Core Services",
                         self.__setUseCertByCmd )
    self.registerCmdOpt( "h", "help", "Shows this help",
                         self.__showHelp )

  def registerCmdOpt( self, shortOption, longOption, helpString, function = False ):
    #TODO: Can't overwrite switches (FATAL)
    self.commandOptionList.append( ( shortOption, longOption, helpString, function ) )

  def getExtraCLICFGFiles( self ):
    if not self.isParsed:
      self.__parseCommandLine()
    return self.cliAdditionalCFGFiles

  def getPositionalArguments( self ):
    if not self.isParsed:
      self.__parseCommandLine()
    return self.commandArgList

  def getUnprocessedSwitches( self ):
    if not self.isParsed:
      self.__parseCommandLine()
    return self.unprocessedSwitches

  def __checkMandatoryOptions( self ):
    try:
      isMandatoryMissing = False
      for optionPath in self.mandatoryEntryList:
        optionPath = self.__getAbsolutePath( optionPath )
        if not gConfigurationData.extractOptionFromCFG( optionPath ):
          gLogger.fatal( "Missing mandatory option in the configuration", optionPath )
          isMandatoryMissing = True
      if isMandatoryMissing:
        return S_ERROR()
      return S_OK()
    except Exception, e:
      gLogger.exception()
      return S_ERROR( str( e ) )

  #TODO: Initialize if not previously initialized
  def initialize( self, componentName ):
    if self.initialized:
      return S_OK()
    self.initialized = True
    #Set that the command line has already been parsed
    self.isParsed = True
    if not self.componentType:
      self.setConfigurationForScript( componentName )
    try:
      retVal = self.__addUserDataToConfiguration()
      gLogger.initialize( self.componentName, self.loggingSection )
      if not retVal[ 'OK' ]:
        return retVal
      retVal = self.__checkMandatoryOptions()
      if not retVal[ 'OK' ]:
        return retVal
    except Exception, e:
      gLogger.exception()
      return S_ERROR( str( e ) )
    return S_OK()

  def loadUserData( self ):
    if self.initialized:
      return S_OK()
    self.initialized = True
    try:
      retVal = self.__addUserDataToConfiguration()

      for optionTuple in self.optionalEntryList:
        optionPath = self.__getAbsolutePath( optionTuple[0] )
        if not gConfigurationData.extractOptionFromCFG( optionPath ):
          gConfigurationData.setOptionInCFG( optionPath, optionTuple[1] )

      gLogger.initialize( self.componentName, self.loggingSection )
      if not retVal[ 'OK' ]:
        return retVal

      retVal = self.__checkMandatoryOptions()
      if not retVal[ 'OK' ]:
        return retVal

    except Exception, e:
      gLogger.exception()
      return S_ERROR( str( e ) )
    return S_OK()

  def __parseCommandLine( self ):
    gLogger.debug( "Parsing command line" )
    shortOption = ""
    longOptionList = []
    for optionTuple in self.commandOptionList:
      if shortOption.find( optionTuple[0] ) < 0:
        shortOption += "%s" % optionTuple[0]
      else:
        gLogger.warn( "Short option -%s has been already defined" % optionTuple[0] )
      if not optionTuple[1] in longOptionList:
        longOptionList.append( "%s" % optionTuple[1] )
      else:
        gLogger.warn( "Long option --%s has been already defined" % optionTuple[1] )

    try:
      opts, args = getopt.gnu_getopt( sys.argv[1:], shortOption, longOptionList )
    except getopt.GetoptError, v:
      # v = option "-k" not recognized
      # print help information and exit
      gLogger.fatal( "Error when parsing command line arguments: %s" % str( v ) )
      self.__showHelp()
      sys.exit( 2 )

    self.cliAdditionalCFGFiles = [ arg for arg in args if arg[-4:] == ".cfg" ]
    self.commandArgList = [ arg for arg in args if not arg[-4:] == ".cfg" ]
    self.parsedOptionList = opts
    self.isParsed = True

  def __loadCFGFiles( self ):
    """
    Load ~/.dirac.cfg
    Load cfg files specified in addCFGFile calls
    Load cfg files with come from the command line
    """
    errorsList = []
    if 'DIRACSYSCONFIG' in os.environ:
      gConfigurationData.loadFile( os.environ[ 'DIRACSYSCONFIG' ] )
    gConfigurationData.loadFile( os.path.expanduser( "~/.dirac.cfg" ) )
    for fileName in self.additionalCFGFiles:
      gLogger.debug( "Loading file %s" % fileName )
      retVal = gConfigurationData.loadFile( fileName )
      if not retVal[ 'OK' ]:
        gLogger.debug( "Could not load file %s: %s" % ( fileName, retVal[ 'Message' ] ) )
        errorsList.append( retVal[ 'Message' ] )
    for fileName in self.cliAdditionalCFGFiles:
      gLogger.debug( "Loading file %s" % fileName )
      retVal = gConfigurationData.loadFile( fileName )
      if not retVal[ 'OK' ]:
        gLogger.debug( "Could not load file %s: %s" % ( fileName, retVal[ 'Message' ] ) )
        errorsList.append( retVal[ 'Message' ] )
    return errorsList

  def __addUserDataToConfiguration( self ):
    if not self.isParsed:
      self.__parseCommandLine()

    errorsList = self.__loadCFGFiles()

    if self.csDisabled:
      newDisabledServers = gConfigurationData.extractOptionFromCFG( "/DIRAC/Configuration/Servers" )
      if newDisabledServers:
        self.csDisabledServers = newDisabledServers
      gConfigurationData.deleteLocalOption( "/DIRAC/Configuration/Servers" )

    if gConfigurationData.getServers():
      retVal = self.syncRemoteConfiguration()
      if not retVal[ 'OK' ]:
        return retVal
    else:
      gLogger.warn( "Running without remote configuration" )

    try:
      if self.componentType == "service":
        self.__setDefaultSection( getServiceSection( self.componentName ) )
      elif self.componentType == "agent":
        self.__setDefaultSection( getAgentSection( self.componentName ) )
      elif self.componentType == "script":
        if self.componentName and self.componentName[0] == "/":
          self.__setDefaultSection( self.componentName )
          self.componentName = self.componentName[1:]
        else:
          self.__setDefaultSection( "/Scripts/%s" % self.componentName )
      else:
        self.__setDefaultSection( "/" )
    except Exception, e:
      errorsList.append( str( e ) )

    self.unprocessedSwitches = []

    for optionName, optionValue in self.parsedOptionList:
      optionName = optionName.replace( "-", "" )
      for definedOptionTuple in self.commandOptionList:
        if optionName == definedOptionTuple[0].replace( ":", "" ) or \
          optionName == definedOptionTuple[1].replace( "=", "" ):
          if definedOptionTuple[3]:
            retVal = definedOptionTuple[3]( optionValue )
            if type( retVal ) != types.DictType:
              errorsList.append( "Callback for switch '%s' does not return S_OK or S_ERROR" % optionName )
            elif not retVal[ 'OK' ]:
              errorsList.append( retVal[ 'Message' ] )
          else:
            self.unprocessedSwitches.append( ( optionName, optionValue ) )

    if self.csDisabled:
      newDisabledServers = gConfigurationData.extractOptionFromCFG( "/DIRAC/Configuration/Servers" )
      if newDisabledServers and not newDisabledServers == self.csDisabledServers:
        self.csDisabledServers = "%s, %s" % ( self.csDisabledServers, newDisabledServers )
      gConfigurationData.deleteLocalOption( "/DIRAC/Configuration/Servers" )

    if len( errorsList ) > 0:
      return S_ERROR( "\n%s" % "\n".join( errorsList ) )
    return S_OK()

  def disableCS( self ):
    self.csDisabled = True

  def enableCS( self ):
    self.csDisabled = False
    if self.csDisabledServers:
      gConfigurationData.setOptionInCFG( "/DIRAC/Configuration/Servers", self.csDisabledServers )
      return self.syncRemoteConfiguration( strict = True )
    return S_OK()


  def syncRemoteConfiguration( self, strict = False ):
    if self.componentName == "Configuration/Server" :
      if gConfigurationData.isMaster():
        gLogger.info( "Starting Master Configuration Server" )
        gRefresher.disable()
        return S_OK()
    retDict = gRefresher.forceRefresh()
    if not retDict['OK']:
      gLogger.error( "Can't update from any server", retDict[ 'Message' ] )
      if strict:
        return retDict
    return S_OK()

  def __setDefaultSection( self, sectionPath ):
    self.currentSectionPath = sectionPath
    self.loggingSection = self.currentSectionPath

  def setConfigurationForServer( self, serviceName ):
    self.componentName = serviceName
    self.componentType = "service"

  def setConfigurationForAgent( self, agentName ):
    self.componentName = agentName
    self.componentType = "agent"

  def setConfigurationForScript( self, scriptName ):
    self.componentName = scriptName
    self.componentType = "script"

  def __setSectionByCmd( self, value ):
    if value[0] != "/":
      return S_ERROR( "%s is not a valid section. It should start with '/'" % value )
    self.currentSectionPath = value
    return S_OK()

  def __setOptionByCmd( self, value ):
    valueList = value.split( "=" )
    if len( valueList ) < 2:
      # FIXME: in the method above an exception is raised, check consitency
      return S_ERROR( "-o expects a option=value argument.\nFor example %s -o Port=1234" % sys.argv[0] )
    self.__setOptionValue( valueList[0] , "=".join( valueList[1:] ) )
    return S_OK()

  def __setUseCertByCmd( self, value ):
    useCert = "no"
    if value.lower() in ( "y", "yes", "true" ):
      useCert = "yes"
    self.__setOptionValue( "/DIRAC/Security/UseServerCertificate", useCert )
    return S_OK()

  def __showHelp( self, dummy = False ):
    gLogger.info( "Usage:" )
    gLogger.info( "  %s (<options>|<cfgFile>)*" % sys.argv[0] )
    gLogger.info( "Options:" )
    for optionTuple in self.commandOptionList:
      gLogger.info( "  -%s  --%s  :  %s" % optionTuple[:3] )
    DIRAC.exit( 0 )

  def deleteOption( self, optionPath ):
    gConfigurationData.deleteOptionInCFG( optionPath )
