class InfoGetter( object ):
  
  def __init__( self, VOExtension ):
    pass
  
  def getInfoToApply( self, args, granularity, statusType = None, status = None, 
                      formerStatus = None, siteType = None, serviceType = None, 
                      resourceType = None, useNewRes = False ):
    return {}
  
  def getNewPolicyType( self, granularity, newStatus ):
    return []
    